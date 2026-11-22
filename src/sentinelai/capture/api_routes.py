"""FastAPI routes for live packet capture.

Provides:
    GET  /capture/interfaces  — list available network interfaces
    GET  /capture/status      — current capture session state
    WS   /ws/live             — WebSocket for real-time flow streaming

Usage: include this router in the main FastAPI app::

    from sentinelai.capture.api_routes import router as capture_router
    app.include_router(capture_router)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .engine import check_pcap_available, list_interfaces, NpcapNotFoundError
from .live_session import LiveSession

logger = logging.getLogger(__name__)

# Triage thresholds (same as /triage and /decision endpoints)
THETA_LOW = 0.20
THETA_HIGH = 0.70

# UNSW-NB15 class labels (index 0 = Normal)
CLASS_LABELS = [
    "Normal", "Fuzzers", "Analysis", "Backdoor", "DoS",
    "Exploit", "Generic", "Reconnaissance", "Shellcode", "Worm",
]


def _get_inference_engine():
    """Lazy-load the shared InferenceEngine singleton.

    Deferred import avoids circular dependencies and ensures the engine
    is only loaded when capture actually starts.
    """
    from sentinelai.inference import InferenceEngine
    return InferenceEngine()


def _triage(probabilities: List[float]) -> Dict[str, Any]:
    """Apply two-stage triage policy to class probabilities.

    Returns a dict with priority, action, and p_attack.
    """
    p_normal = probabilities[0] if probabilities else 0.0
    p_attack = 1.0 - p_normal

    if p_attack >= THETA_HIGH:
        return {
            "priority": "critical" if p_attack >= 0.90 else "high",
            "action": "escalate",
            "p_attack": round(p_attack, 4),
        }
    elif p_attack >= THETA_LOW:
        return {
            "priority": "medium",
            "action": "review",
            "p_attack": round(p_attack, 4),
        }
    else:
        return {
            "priority": "low",
            "action": "log",
            "p_attack": round(p_attack, 4),
        }


async def _predict_and_triage(features: dict) -> dict:
    """Run inference + triage on a 76-feature dict.

    Called by LiveSession for each completed flow.  Runs the CPU-bound
    model prediction in the default executor to avoid blocking the
    event loop.
    """
    engine = _get_inference_engine()
    loop = asyncio.get_running_loop()

    # Pass the feature dict directly — InferenceEngine.predict()
    # expects a dict mapping feature names to values, not a DataFrame.
    result = await loop.run_in_executor(None, engine.predict, features)

    # Apply triage
    probs = result.get("probabilities", [])
    decision = _triage(probs)

    return {
        "prediction": {
            "class_id": result.get("class_id"),
            "class_label": result.get("class_label"),
            "probabilities": probs,
            "model_version": result.get("model_version"),
        },
        "decision": decision,
    }


# ======================================================================
#  WebSocket connection manager
# ======================================================================

class LiveCaptureManager:
    """Manages WebSocket connections and the active capture session."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.session: Optional[LiveSession] = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active_connections.append(ws)
        logger.info("WS client connected (%d total)",
                     len(self.active_connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active_connections:
            self.active_connections.remove(ws)
        logger.info("WS client disconnected (%d remaining)",
                     len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected clients."""
        dead: List[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def start_capture(
        self,
        interface: str,
        bpf_filter: str = "",
        predict_fn=None,
        idle_timeout: float = 30.0,
        active_timeout: float = 300.0,
    ) -> dict:
        """Start a new capture session."""
        if self.session and self.session.is_running:
            await self.session.stop()

        self.session = LiveSession(
            interface=interface,
            broadcast=self.broadcast,
            bpf_filter=bpf_filter,
            predict_fn=predict_fn,
            idle_timeout=idle_timeout,
            active_timeout=active_timeout,
        )
        await self.session.start()

        return {
            "status": "started",
            "interface": interface,
            "filter": bpf_filter,
        }

    async def stop_capture(self) -> dict:
        """Stop the current capture session."""
        if self.session and self.session.is_running:
            stats = self.session.get_stats()
            await self.session.stop()
            self.session = None
            return {"status": "stopped", "final_stats": stats}
        return {"status": "not_running"}

    async def pause_capture(self) -> dict:
        if self.session and self.session.is_running:
            self.session.pause()
            return {"status": "paused"}
        return {"status": "not_running"}

    async def resume_capture(self) -> dict:
        if self.session and self.session.is_running:
            self.session.resume()
            return {"status": "resumed"}
        return {"status": "not_running"}


# Singleton manager
_manager = LiveCaptureManager()


# ======================================================================
#  Router
# ======================================================================

router = APIRouter(tags=["capture"])


@router.get("/capture/interfaces")
async def get_interfaces():
    """List available network interfaces with their IPv4 addresses.

    Returns a list of ``{name, addresses, is_up}`` dicts.
    The user selects one to pass in the WebSocket "start" command.
    """
    try:
        interfaces = list_interfaces()
        return {"interfaces": interfaces}
    except Exception as exc:
        logger.error("Failed to list interfaces: %s", exc)
        return {
            "interfaces": [],
            "error": str(exc),
            "hint": "Ensure Npcap is installed (Windows) or libpcap (Linux).",
        }


@router.get("/capture/check-pcap")
async def check_pcap():
    """Check whether Npcap (Windows) or libpcap (Linux/macOS) is available.

    Returns ``{available, backend, message, hint}`` so the frontend can
    show a user-friendly error with install instructions before the user
    tries to start a capture.
    """
    return check_pcap_available()


@router.get("/capture/status")
async def get_capture_status():
    """Current capture session status and statistics."""
    if _manager.session and _manager.session.is_running:
        return {
            "capturing": True,
            "stats": _manager.session.get_stats(),
        }
    return {"capturing": False}


@router.websocket("/ws/live")
async def live_capture_ws(websocket: WebSocket):
    """WebSocket endpoint for live capture streaming.

    Client sends JSON control messages::

        {"action": "start", "interface": "Ethernet", "filter": "tcp port 80"}
        {"action": "stop"}
        {"action": "pause"}
        {"action": "resume"}

    Server sends two message types::

        {"type": "flow_result", ...}    — completed flow with prediction
        {"type": "capture_stats", ...}  — periodic statistics
    """
    await _manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "").lower()

            if action == "start":
                # If a session is already running, just acknowledge
                # (prevents duplicate start from multiple WS connections)
                if _manager.session and _manager.session.is_running:
                    await websocket.send_json({
                        "type": "control",
                        "status": "started",
                        "interface": _manager.session.interface,
                        "filter": "",
                    })
                    continue

                # Pre-flight: check pcap library availability
                pcap_status = check_pcap_available()
                if not pcap_status["available"]:
                    await websocket.send_json({
                        "type": "error",
                        "message": pcap_status["message"],
                        "hint": pcap_status.get("hint", ""),
                    })
                    continue

                interface = data.get("interface", "")
                bpf_filter = data.get("filter", "")

                if not interface:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No interface specified.",
                    })
                    continue

                # Validate interface exists
                available = list_interfaces()
                valid_names = {i["name"] for i in available}
                if interface not in valid_names:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown interface: {interface}",
                        "available": [i["name"] for i in available],
                    })
                    continue

                try:
                    result = await _manager.start_capture(
                        interface=interface,
                        bpf_filter=bpf_filter,
                        predict_fn=_predict_and_triage,
                    )
                    await websocket.send_json({
                        "type": "control",
                        **result,
                    })
                except Exception as exc:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to start capture: {exc}",
                    })

            elif action == "stop":
                result = await _manager.stop_capture()
                await websocket.send_json({
                    "type": "control",
                    **result,
                })

            elif action == "pause":
                result = await _manager.pause_capture()
                await websocket.send_json({
                    "type": "control",
                    **result,
                })

            elif action == "resume":
                result = await _manager.resume_capture()
                await websocket.send_json({
                    "type": "control",
                    **result,
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}",
                })

    except WebSocketDisconnect:
        _manager.disconnect(websocket)
        # If no clients remain, stop capture
        if not _manager.active_connections:
            await _manager.stop_capture()
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        _manager.disconnect(websocket)