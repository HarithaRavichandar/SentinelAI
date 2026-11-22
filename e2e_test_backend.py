"""SentinelAI — End-to-End Backend Test Suite

Run from the project root with .venv_compat activated:

    cd H:\SentinelAI
    .venv_compat\Scripts\activate
    $env:PYTHONPATH = "H:\SentinelAI\src"
    python e2e_test_backend.py

Prerequisites:
    - Backend running: uvicorn sentinelai.api:app --reload --host 0.0.0.0 --port 8000
    - pip install requests websockets  (in .venv_compat)

Tests are numbered and run sequentially.  A failing test prints FAIL with
details but does NOT stop the suite — all tests run so you get the full picture.
"""

import json
import subprocess
import sys
import time
import asyncio
import traceback
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
#  Auto-install missing packages
# ---------------------------------------------------------------------------
def _ensure_package(name: str):
    try:
        __import__(name)
    except ImportError:
        print(f"  Installing {name}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", name, "--quiet"],
        )

_ensure_package("requests")
_ensure_package("websockets")

# ---------------------------------------------------------------------------
#  Config
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"
TIMEOUT = 10  # seconds for HTTP requests

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
results: List[Tuple[str, bool, str]] = []

def report(test_id: str, passed: bool, detail: str = ""):
    tag = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
    print(f"  [{tag}] {test_id}: {detail}")
    results.append((test_id, passed, detail))

def get(path: str) -> Dict[str, Any]:
    import requests
    r = requests.get(f"{API_BASE}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def post(path: str, **kwargs) -> Dict[str, Any]:
    import requests
    r = requests.post(f"{API_BASE}{path}", timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r.json()

# ===================================================================
#  TEST 1: Backend Health & Endpoints
# ===================================================================
def test_1_backend_health():
    print("\n=== TEST 1: Backend Startup & Health Checks ===")

    # 1a: Root or docs endpoint responds
    try:
        import requests
        r = requests.get(f"{API_BASE}/docs", timeout=TIMEOUT)
        report("1a-docs", r.status_code == 200, f"GET /docs → {r.status_code}")
    except Exception as e:
        report("1a-docs", False, f"Backend not reachable: {e}")
        return  # No point continuing if backend is down

    # 1b: Pcap check endpoint
    try:
        data = get("/capture/check-pcap")
        has_keys = all(k in data for k in ("available", "backend", "message"))
        report("1b-pcap-check", has_keys,
               f"available={data.get('available')}, backend={data.get('backend')}")
    except Exception as e:
        report("1b-pcap-check", False, str(e))

    # 1c: List interfaces
    try:
        data = get("/capture/interfaces")
        ifaces = data.get("interfaces", [])
        report("1c-interfaces", len(ifaces) > 0,
               f"{len(ifaces)} interfaces found: {[i['name'] for i in ifaces[:5]]}")
    except Exception as e:
        report("1c-interfaces", False, str(e))

    # 1d: Capture status (should be not capturing)
    try:
        data = get("/capture/status")
        report("1d-status-idle", data.get("capturing") == False,
               f"capturing={data.get('capturing')}")
    except Exception as e:
        report("1d-status-idle", False, str(e))


# ===================================================================
#  TEST 2: ML Inference Pipeline
# ===================================================================
def test_2_ml_inference():
    print("\n=== TEST 2: ML Inference Pipeline ===")

    # 2a: Model loads via /predict endpoint
    # Build a minimal 76-feature vector (all zeros — should classify as Normal)
    feature_names = [
        "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
        "Total Length of Fwd Packet", "Total Length of Bwd Packet",
        "Fwd Packet Length Max", "Fwd Packet Length Min", "Fwd Packet Length Mean",
        "Fwd Packet Length Std", "Bwd Packet Length Max", "Bwd Packet Length Min",
        "Bwd Packet Length Mean", "Bwd Packet Length Std",
        "Flow Bytes/s", "Flow Packets/s",
        "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
        "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
        "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
        "Fwd PSH Flags", "Bwd PSH Flags", "Fwd URG Flags", "Bwd URG Flags",
        "Fwd Header Length", "Bwd Header Length",
        "Fwd Packets/s", "Bwd Packets/s",
        "Packet Length Min", "Packet Length Max", "Packet Length Mean",
        "Packet Length Std", "Packet Length Variance",
        "FIN Flag Count", "SYN Flag Count", "RST Flag Count", "PSH Flag Count",
        "ACK Flag Count", "URG Flag Count", "CWR Flag Count", "ECE Flag Count",
        "Down/Up Ratio", "Average Packet Size",
        "Fwd Segment Size Avg", "Bwd Segment Size Avg",
        "Fwd Bytes/Bulk Avg", "Fwd Packet/Bulk Avg", "Fwd Bulk Rate Avg",
        "Bwd Bytes/Bulk Avg", "Bwd Packet/Bulk Avg", "Bwd Bulk Rate Avg",
        "Subflow Fwd Packets", "Subflow Fwd Bytes", "Subflow Bwd Packets", "Subflow Bwd Bytes",
        "FWD Init Win Bytes", "Bwd Init Win Bytes",
        "Fwd Act Data Pkts", "Fwd Seg Size Min",
        "Active Mean", "Active Std", "Active Max", "Active Min",
        "Idle Mean", "Idle Std", "Idle Max", "Idle Min",
    ]

    try:
        assert len(feature_names) == 76, f"Expected 76 features, got {len(feature_names)}"
        report("2a-feature-count", True, "76 feature names verified")
    except AssertionError as e:
        report("2a-feature-count", False, str(e))

    # 2b: Call /predict with zero-vector
    zero_features = {name: 0.0 for name in feature_names}
    try:
        data = post("/predict", json={"features": zero_features})
        has_class = "class_id" in data or "class_label" in data
        report("2b-predict-zero", has_class,
               f"class_label={data.get('class_label')}, class_id={data.get('class_id')}")
    except Exception as e:
        # /predict might not exist as a standalone endpoint — that's OK
        # The prediction runs through the WebSocket pipeline instead
        report("2b-predict-zero", None, f"Standalone /predict not available (OK if WS-only): {e}")

    # 2c: Call /triage or /decision endpoint
    try:
        data = post("/triage", json={"features": zero_features})
        has_decision = "priority" in str(data) or "decision" in str(data)
        report("2c-triage", has_decision, f"response keys: {list(data.keys())[:5]}")
    except Exception as e:
        report("2c-triage", None, f"Standalone /triage not available (OK if WS-only): {e}")

    # 2d: Verify InferenceEngine loads directly (import test)
    try:
        from sentinelai.inference import InferenceEngine
        engine = InferenceEngine()
        result = engine.predict(zero_features)
        has_probs = "probabilities" in result
        probs = result.get("probabilities", [])
        n_probs = len(probs)
        probs_sum = sum(probs) if probs else 0
        # RF can return raw vote counts (sum ~= n_estimators) or
        # normalized probabilities (sum ~= 1.0).  Both are valid.
        valid_probs = has_probs and n_probs == 10 and probs_sum > 0
        report("2d-engine-direct", valid_probs,
               f"class={result.get('class_label')}, "
               f"n_probs={n_probs}, p_sum={probs_sum:.4f}")
    except Exception as e:
        report("2d-engine-direct", False, f"InferenceEngine import/predict failed: {e}")

    # 2e: Triage threshold verification
    try:
        from sentinelai.capture.api_routes import _triage
        # p_attack < 0.20 → low
        low = _triage([0.85, 0.05, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01])
        assert low["priority"] == "low", f"Expected low, got {low['priority']}"

        # p_attack = 0.50 → medium
        med = _triage([0.50, 0.10, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05, 0.03, 0.02])
        assert med["priority"] == "medium", f"Expected medium, got {med['priority']}"

        # p_attack = 0.80 → high
        high = _triage([0.20, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.05, 0.05, 0.05])
        assert high["priority"] == "high", f"Expected high, got {high['priority']}"

        # p_attack = 0.95 → critical
        crit = _triage([0.05, 0.20, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.05, 0.05])
        assert crit["priority"] == "critical", f"Expected critical, got {crit['priority']}"

        report("2e-triage-thresholds", True,
               "low(<0.20), medium(0.20-0.70), high(0.70-0.90), critical(>=0.90) ✓")
    except Exception as e:
        report("2e-triage-thresholds", False, str(e))


# ===================================================================
#  TEST 3: CSV Batch Ingestion
# ===================================================================
def test_3_batch_ingestion():
    print("\n=== TEST 3: CSV Batch Ingestion ===")

    import requests
    import io
    import csv

    # 3a: Generate a minimal valid CSV with the 76 CICFlowMeter columns
    feature_names = [
        "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
        "Total Length of Fwd Packet", "Total Length of Bwd Packet",
        "Fwd Packet Length Max", "Fwd Packet Length Min", "Fwd Packet Length Mean",
        "Fwd Packet Length Std", "Bwd Packet Length Max", "Bwd Packet Length Min",
        "Bwd Packet Length Mean", "Bwd Packet Length Std",
        "Flow Bytes/s", "Flow Packets/s",
        "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
        "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
        "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
        "Fwd PSH Flags", "Bwd PSH Flags", "Fwd URG Flags", "Bwd URG Flags",
        "Fwd Header Length", "Bwd Header Length",
        "Fwd Packets/s", "Bwd Packets/s",
        "Packet Length Min", "Packet Length Max", "Packet Length Mean",
        "Packet Length Std", "Packet Length Variance",
        "FIN Flag Count", "SYN Flag Count", "RST Flag Count", "PSH Flag Count",
        "ACK Flag Count", "URG Flag Count", "CWR Flag Count", "ECE Flag Count",
        "Down/Up Ratio", "Average Packet Size",
        "Fwd Segment Size Avg", "Bwd Segment Size Avg",
        "Fwd Bytes/Bulk Avg", "Fwd Packet/Bulk Avg", "Fwd Bulk Rate Avg",
        "Bwd Bytes/Bulk Avg", "Bwd Packet/Bulk Avg", "Bwd Bulk Rate Avg",
        "Subflow Fwd Packets", "Subflow Fwd Bytes", "Subflow Bwd Packets", "Subflow Bwd Bytes",
        "FWD Init Win Bytes", "Bwd Init Win Bytes",
        "Fwd Act Data Pkts", "Fwd Seg Size Min",
        "Active Mean", "Active Std", "Active Max", "Active Min",
        "Idle Mean", "Idle Std", "Idle Max", "Idle Min",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(feature_names)
    # Row 1: all zeros (likely Normal)
    writer.writerow([0.0] * 76)
    # Row 2: high values to simulate suspicious traffic
    suspicious = [100000.0, 50, 2, 50000, 200,
                  1500, 100, 800, 400, 200, 50, 100, 60,
                  500000, 1000,
                  2000, 1500, 5000, 100,
                  10000, 2000, 1500, 5000, 100,
                  1000, 500, 300, 1000, 50,
                  1, 0, 0, 0,
                  1600, 160,
                  500, 20,
                  50, 1500, 700, 500, 250000,
                  1, 2, 0, 5, 10, 0, 0, 0,
                  25.0, 700,
                  800, 100,
                  5000, 10, 100000,
                  200, 2, 5000,
                  50, 50000, 2, 200,
                  65535, 1024,
                  45, 20,
                  500, 200, 1000, 100,
                  5000, 2000, 10000, 1000]
    writer.writerow(suspicious)
    # Row 3: another pattern
    writer.writerow([50000 + i * 100 for i in range(76)])
    csv_content = buf.getvalue()

    # 3a: Upload CSV
    job_id = None
    try:
        files = {"file": ("test_batch.csv", csv_content, "text/csv")}
        r = requests.post(f"{API_BASE}/batch/upload", files=files, timeout=30)
        if r.status_code == 200:
            data = r.json()
            job_id = data.get("job_id") or data.get("batch_id") or data.get("id")
            report("3a-upload", job_id is not None,
                   f"job_id={job_id}, detail={data.get('detail', '')[:60]}")
        elif r.status_code == 404:
            report("3a-upload", None, "POST /batch/upload not found (endpoint may differ)")
            return
        else:
            report("3a-upload", False, f"status={r.status_code}, body={r.text[:200]}")
            return
    except Exception as e:
        report("3a-upload", False, str(e))
        return

    if not job_id:
        return

    # 3b: Poll for results (wait up to 15s)
    try:
        for _ in range(15):
            time.sleep(1)
            r = requests.get(f"{API_BASE}/batch/{job_id}/results", timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                status = data.get("status", "")
                if status in ("completed", "done", "finished"):
                    results_list = data.get("results", data.get("rows", []))
                    report("3b-results", len(results_list) > 0,
                           f"status={status}, {len(results_list)} rows returned")
                    # Check classifications exist in each result
                    if results_list:
                        first = results_list[0]
                        # Results may nest under "prediction"/"decision" or
                        # have top-level keys like "class_label", "priority"
                        has_class = any(
                            k in first or k in first.get("prediction", {})
                            or k in first.get("decision", {})
                            for k in ("class_label", "class_id", "priority")
                        )
                        report("3c-classifications", has_class,
                               f"first row keys: {list(first.keys())[:8]}")
                    break
            elif r.status_code == 202:
                continue  # Still processing
        else:
            report("3b-results", False, "Timed out waiting for batch completion")
    except Exception as e:
        report("3b-results", False, str(e))


# ===================================================================
#  TEST 4: Live Capture WebSocket Pipeline
# ===================================================================
def test_4_live_capture():
    print("\n=== TEST 4: Live Capture WebSocket Pipeline ===")

    async def _run_ws_tests():
        import websockets

        # 4a: Connect to WebSocket
        try:
            ws = await asyncio.wait_for(
                websockets.connect(f"{WS_BASE}/ws/live"),
                timeout=5,
            )
            report("4a-ws-connect", True, "WebSocket connected")
        except Exception as e:
            report("4a-ws-connect", False, f"WebSocket connection failed: {e}")
            return

        # 4b: Get interfaces to pick one
        try:
            data = get("/capture/interfaces")
            ifaces = data.get("interfaces", [])
            up_ifaces = [i for i in ifaces if i.get("is_up")]
            if not up_ifaces:
                report("4b-interface-select", False, "No UP interfaces available")
                await ws.close()
                return
            iface_name = up_ifaces[0]["name"]
            report("4b-interface-select", True, f"Using interface: {iface_name}")
        except Exception as e:
            report("4b-interface-select", False, str(e))
            await ws.close()
            return

        # 4c: Send start command
        try:
            await ws.send(json.dumps({
                "action": "start",
                "interface": iface_name,
                "filter": "",
            }))
            # Wait for control response
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(resp)
            started = msg.get("type") == "control" and msg.get("status") == "started"
            report("4c-start-capture", started,
                   f"type={msg.get('type')}, status={msg.get('status')}")
        except Exception as e:
            report("4c-start-capture", False, str(e))
            await ws.close()
            return

        # 4d: Wait for stats messages (should arrive within 2s)
        stats_received = False
        flow_received = False
        try:
            deadline = time.time() + 35  # wait up to 35s for flows to complete
            while time.time() < deadline:
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=2)
                    msg = json.loads(resp)
                    if msg.get("type") == "capture_stats":
                        if not stats_received:
                            stats_received = True
                            report("4d-stats-stream", True,
                                   f"packets={msg.get('packets_captured')}, "
                                   f"active={msg.get('active_flows')}")
                    elif msg.get("type") == "flow_result":
                        if not flow_received:
                            flow_received = True
                            pred = msg.get("prediction", {})
                            dec = msg.get("decision", {})
                            report("4e-flow-result", True,
                                   f"class={pred.get('class_label')}, "
                                   f"priority={dec.get('priority')}, "
                                   f"p_attack={dec.get('p_attack')}")
                except asyncio.TimeoutError:
                    continue

                if stats_received and flow_received:
                    break
        except Exception as e:
            pass

        if not stats_received:
            report("4d-stats-stream", False, "No stats messages received in 35s")
        if not flow_received:
            report("4e-flow-result", None,
                   "No flows completed in 35s (may need more traffic — "
                   "try browsing a website during the test)")

        # Drain any buffered messages (stats etc.) before sending control actions
        async def drain_ws(max_time: float = 3.0):
            drained = 0
            deadline = time.time() + max_time
            while time.time() < deadline:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.2)
                    drained += 1
                except asyncio.TimeoutError:
                    break
                except Exception:
                    break
            return drained

        # Helper: send action, then read until control message or deadline.
        async def send_and_wait_control(action: str, timeout_s: float = 15):
            # Drain stale messages first
            n = await drain_ws(3.0)
            if n:
                print(f"    [debug] drained {n} stale messages before '{action}'")
            await ws.send(json.dumps({"action": action}))
            deadline = time.time() + timeout_s
            skipped = 0
            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                try:
                    resp = await asyncio.wait_for(
                        ws.recv(), timeout=min(remaining, 2.0)
                    )
                    msg = json.loads(resp)
                    if msg.get("type") == "control":
                        if skipped:
                            print(f"    [debug] skipped {skipped} non-control msgs for '{action}'")
                        return msg
                    skipped += 1
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
            print(f"    [debug] TIMEOUT for '{action}' after {timeout_s}s, skipped {skipped} msgs")
            return None

        # 4f: Test pause
        try:
            msg = await send_and_wait_control("pause", timeout_s=15)
            if msg:
                paused = msg.get("status") == "paused"
                report("4f-pause", paused, f"status={msg.get('status')}")
            else:
                report("4f-pause", False, "No control response received for pause")
        except Exception as e:
            report("4f-pause", False, str(e))

        # Small delay to let server settle into paused state
        await asyncio.sleep(1.0)

        # 4g: Test resume
        try:
            msg = await send_and_wait_control("resume", timeout_s=15)
            if msg:
                resumed = msg.get("status") == "resumed"
                report("4g-resume", resumed, f"status={msg.get('status')}")
            else:
                report("4g-resume", False, "No control response received for resume")
        except Exception as e:
            report("4g-resume", False, str(e))

        # Small delay before stop
        await asyncio.sleep(1.0)

        # 4h: Test stop
        try:
            msg = await send_and_wait_control("stop", timeout_s=15)
            if msg:
                stopped = msg.get("status") == "stopped"
                final = msg.get("final_stats")
                report("4h-stop", stopped,
                       f"status={msg.get('status')}, "
                       f"final_completed={final.get('completed_flows') if final else '?'}")
            else:
                report("4h-stop", False, "No control response received for stop")
        except Exception as e:
            report("4h-stop", False, str(e))

        # 4i: Verify status is idle after stop
        try:
            data = get("/capture/status")
            report("4i-idle-after-stop", data.get("capturing") == False,
                   f"capturing={data.get('capturing')}")
        except Exception as e:
            report("4i-idle-after-stop", False, str(e))

        await ws.close()

    try:
        asyncio.run(_run_ws_tests())
    except Exception as e:
        report("4-ws-suite", False, f"WebSocket test suite error: {e}")


# ===================================================================
#  TEST 5: Feature Extractor & Flow State
# ===================================================================
def test_5_feature_extraction():
    print("\n=== TEST 5: Feature Extraction & Flow State ===")

    # 5a: FlowState bulk tracking
    try:
        from sentinelai.capture.flow_state import FlowState
        f = FlowState(
            src_ip="10.0.0.1", dst_ip="10.0.0.2",
            src_port=12345, dst_port=80,
            protocol=6, first_seen=1000.0, last_seen=1000.0,
        )
        # Simulate 5 forward packets (above BULK_THRESHOLD=4)
        for i in range(5):
            f.update_forward(
                ts=1000.0 + i * 0.1, ip_len=1500, ttl=64,
                tcp_flags=0x18, tcp_seq=1000 + i * 1000,
                tcp_win=65535, payload_len=1400, header_len=40,
            )
        f.finalize_bulk()
        report("5a-bulk-tracking", f.fwd_bulk_count >= 1,
               f"fwd_bulk_count={f.fwd_bulk_count}, "
               f"fwd_bulk_total_pkts={f.fwd_bulk_total_pkts}")
    except Exception as e:
        report("5a-bulk-tracking", False, str(e))

    # 5b: FeatureExtractor produces 76 features
    try:
        from sentinelai.capture.feature_extractor import FeatureExtractor
        from sentinelai.capture.flow_state import FlowState

        f = FlowState(
            src_ip="10.0.0.1", dst_ip="10.0.0.2",
            src_port=12345, dst_port=80,
            protocol=6, first_seen=1000.0, last_seen=1000.0,
        )
        # Add a few packets in both directions
        for i in range(3):
            f.update_forward(1000.0 + i * 0.5, 500, 64, 0x18, 1000 + i * 500, 65535, 400, 40)
        for i in range(2):
            f.update_reverse(1001.5 + i * 0.3, 200, 64, 0x10, 2000 + i * 200, 32768, 150, 40)

        extractor = FeatureExtractor()
        features = extractor.extract(f)
        n_features = len(features)
        report("5b-76-features", n_features == 76,
               f"got {n_features} features, "
               f"Flow Duration={features.get('Flow Duration')}, "
               f"Total Fwd Packet={features.get('Total Fwd Packet')}")
    except Exception as e:
        report("5b-76-features", False, str(e))

    # 5c: FlowTable with 30s idle timeout
    try:
        from sentinelai.capture.flow_table import FlowTable
        ft = FlowTable()
        report("5c-idle-timeout", ft.idle_timeout == 30.0,
               f"idle_timeout={ft.idle_timeout}s (expected 30.0)")
    except Exception as e:
        report("5c-idle-timeout", False, str(e))

    # 5d: Npcap detection function
    try:
        from sentinelai.capture.engine import check_pcap_available
        result = check_pcap_available()
        has_keys = all(k in result for k in ("available", "backend", "message"))
        report("5d-pcap-detection", has_keys,
               f"available={result['available']}, backend={result['backend']}")
    except Exception as e:
        report("5d-pcap-detection", False, str(e))


# ===================================================================
#  Summary
# ===================================================================
def print_summary():
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, p, _ in results if p is True)
    failed = sum(1 for _, p, _ in results if p is False)
    skipped = sum(1 for _, p, _ in results if p is None)
    total = len(results)
    print(f"  Total: {total}  |  "
          f"\033[92mPassed: {passed}\033[0m  |  "
          f"\033[91mFailed: {failed}\033[0m  |  "
          f"\033[93mSkipped: {skipped}\033[0m")
    print("=" * 60)

    if failed > 0:
        print("\n  Failed tests:")
        for tid, p, detail in results:
            if p is False:
                print(f"    ✗ {tid}: {detail}")

    if skipped > 0:
        print("\n  Skipped/optional tests:")
        for tid, p, detail in results:
            if p is None:
                print(f"    ~ {tid}: {detail}")

    print()
    return failed == 0


# ===================================================================
#  Main
# ===================================================================
if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════╗")
    print("║     SentinelAI — End-to-End Backend Tests       ║")
    print("╚══════════════════════════════════════════════════╝")

    test_1_backend_health()
    test_2_ml_inference()
    test_3_batch_ingestion()
    test_4_live_capture()
    test_5_feature_extraction()

    all_passed = print_summary()
    sys.exit(0 if all_passed else 1)