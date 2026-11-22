"""Live capture session orchestrator.

Ties together: CaptureEngine → FlowTable → FeatureExtractor →
ML prediction → WebSocket broadcast.

A LiveSession is created when a WebSocket client sends a "start" command,
and destroyed on "stop" or disconnect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .engine import CaptureEngine
from .feature_extractor import FeatureExtractor
from .flow_state import FlowState
from .flow_table import FlowTable

logger = logging.getLogger(__name__)


# How often to broadcast stats to WS clients (seconds)
STATS_INTERVAL = 1.0

# How often to sweep the flow table for expired flows (seconds)
SWEEP_INTERVAL = 5.0

# Max items in the packet queue before dropping
PACKET_QUEUE_SIZE = 10_000


@dataclass
class CaptureStats:
    """Running statistics for the current capture session."""
    started_at: float = 0.0
    packets_captured: int = 0
    packets_dropped: int = 0
    active_flows: int = 0
    completed_flows: int = 0
    flows_per_second: float = 0.0
    alerts: Dict[str, int] = field(default_factory=lambda: {
        "critical": 0, "high": 0, "medium": 0, "low": 0,
    })
    _prev_completed: int = 0
    _prev_time: float = 0.0

    def update_rate(self, now: float, completed: int) -> None:
        dt = now - self._prev_time if self._prev_time else 1.0
        if dt > 0:
            self.flows_per_second = round(
                (completed - self._prev_completed) / dt, 1
            )
        self._prev_completed = completed
        self._prev_time = now

    def to_dict(self) -> dict:
        return {
            "type": "capture_stats",
            "elapsed_seconds": round(time.time() - self.started_at, 1),
            "packets_captured": self.packets_captured,
            "packets_dropped": self.packets_dropped,
            "active_flows": self.active_flows,
            "completed_flows": self.completed_flows,
            "flows_per_second": self.flows_per_second,
            "alerts_count": dict(self.alerts),
        }


# Type alias for the broadcast callback
BroadcastFn = Callable[[dict], Coroutine[Any, Any, None]]


class LiveSession:
    """Orchestrates a single live capture session.

    Parameters
    ----------
    interface : str
        Network interface to capture on.
    bpf_filter : str
        Optional BPF filter expression.
    broadcast : BroadcastFn
        Async callable that sends a JSON-serialisable dict to all
        connected WebSocket clients.
    predict_fn : callable | None
        ``async def predict(features: dict) -> dict`` that runs the ML
        pipeline and returns ``{"prediction": {...}, "decision": {...}}``.
        If None, flows are emitted without predictions.
    """

    def __init__(
        self,
        interface: str,
        broadcast: BroadcastFn,
        bpf_filter: str = "",
        predict_fn: Optional[Callable] = None,
        idle_timeout: float = 30.0,
        active_timeout: float = 300.0,
    ):
        self.interface = interface
        self.bpf_filter = bpf_filter
        self._broadcast = broadcast
        self._predict_fn = predict_fn

        # Core components
        self._flow_table = FlowTable(
            idle_timeout=idle_timeout,
            active_timeout=active_timeout,
        )
        self._feature_extractor = FeatureExtractor()

        # Async infrastructure
        self._packet_queue: asyncio.Queue = asyncio.Queue(
            maxsize=PACKET_QUEUE_SIZE,
        )
        self._engine: Optional[CaptureEngine] = None
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._stats = CaptureStats()
        self._paused = False

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Start the capture engine and processing loops."""
        if self._running:
            logger.warning("Session already running")
            return

        loop = asyncio.get_running_loop()

        self._engine = CaptureEngine(
            interface=self.interface,
            queue=self._packet_queue,
            loop=loop,
            bpf_filter=self.bpf_filter,
        )

        self._running = True
        self._stats = CaptureStats(started_at=time.time())

        # Start the scapy sniff thread
        self._engine.start()

        # Start async processing tasks
        self._tasks = [
            asyncio.create_task(self._process_packets(), name="process"),
            asyncio.create_task(self._sweep_loop(), name="sweep"),
            asyncio.create_task(self._stats_loop(), name="stats"),
        ]

        logger.info("LiveSession started on %s", self.interface)

    async def stop(self) -> None:
        """Stop the capture engine and processing loops."""
        self._running = False

        if self._engine:
            self._engine.stop()

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("LiveSession stopped")

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    #  Main packet processing loop
    # ------------------------------------------------------------------
    async def _process_packets(self) -> None:
        """Consume packets from the queue, update flows, emit results."""
        while self._running:
            try:
                pkt_tuple = await asyncio.wait_for(
                    self._packet_queue.get(), timeout=0.5,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if self._paused:
                continue

            (
                ts, src_ip, dst_ip, src_port, dst_port, protocol,
                ip_len, ttl, tcp_flags, tcp_seq, tcp_win, payload_len,
                header_len,
            ) = pkt_tuple

            # Feed into flow table
            completed = self._flow_table.process_packet(
                ts, src_ip, dst_ip, src_port, dst_port, protocol,
                ip_len, ttl, tcp_flags, tcp_seq, tcp_win, payload_len,
                header_len,
            )

            if completed:
                await self._handle_completed_flow(completed)

    async def _handle_completed_flow(self, flow: FlowState) -> None:
        """Extract features, run prediction, broadcast result."""
        # Extract the full 76-feature CICFlowMeter vector
        features = self._feature_extractor.extract(flow)

        # Run ML prediction + triage (if wired up)
        prediction = None
        decision = None
        if self._predict_fn:
            try:
                result = await self._predict_fn(dict(features))
                prediction = result.get("prediction")
                decision = result.get("decision")
            except Exception as exc:
                logger.warning("Prediction failed for flow: %s", exc)

        # Update alert stats by priority
        priority = "low"
        if decision and isinstance(decision, dict):
            priority = decision.get("priority", "low").lower()
        if priority in self._stats.alerts:
            self._stats.alerts[priority] += 1

        # Broadcast to WebSocket clients
        message = {
            "type": "flow_result",
            "timestamp": time.time(),
            "flow_id": f"{flow.src_ip}:{flow.src_port}-"
                       f"{flow.dst_ip}:{flow.dst_port}-"
                       f"{flow.protocol}",
            "flow_summary": {
                "src_ip": flow.src_ip,
                "dst_ip": flow.dst_ip,
                "src_port": flow.src_port,
                "dst_port": flow.dst_port,
                "protocol": flow.protocol,
                "duration": round(flow.duration, 4),
                "sbytes": flow.sbytes,
                "dbytes": flow.dbytes,
                "spkts": flow.spkts,
                "dpkts": flow.dpkts,
            },
            "prediction": prediction,
            "decision": decision,
        }

        try:
            await self._broadcast(message)
        except Exception as exc:
            logger.warning("Broadcast failed: %s", exc)

    # ------------------------------------------------------------------
    #  Background loops
    # ------------------------------------------------------------------
    async def _sweep_loop(self) -> None:
        """Periodically sweep the flow table for timed-out flows."""
        while self._running:
            try:
                await asyncio.sleep(SWEEP_INTERVAL)
                expired = self._flow_table.sweep_expired()
                for flow in expired:
                    await self._handle_completed_flow(flow)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Sweep error: %s", exc)

    async def _stats_loop(self) -> None:
        """Periodically broadcast capture statistics."""
        while self._running:
            try:
                await asyncio.sleep(STATS_INTERVAL)

                # Skip broadcasting when paused so the UI appears frozen
                if self._paused:
                    continue

                if self._engine:
                    self._stats.packets_captured = self._engine.packets_captured
                    self._stats.packets_dropped = self._engine.packets_dropped

                ft_stats = self._flow_table.get_stats()
                self._stats.active_flows = ft_stats["active_flows"]
                self._stats.completed_flows = ft_stats["total_completed"]
                self._stats.update_rate(time.time(), ft_stats["total_completed"])

                await self._broadcast(self._stats.to_dict())

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Stats broadcast error: %s", exc)

    # ------------------------------------------------------------------
    #  Info
    # ------------------------------------------------------------------
    def get_stats(self) -> dict:
        return self._stats.to_dict()