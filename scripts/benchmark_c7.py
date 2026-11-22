"""
Stage F – Runtime benchmark: c7_candidate vs fresh
Measures: model load time, inference latency, SHAP computation time, memory usage.
"""
import time
import json
import tracemalloc
from pathlib import Path
from statistics import mean, stdev

ITERATIONS = 20  # inference/SHAP runs per model

fixture_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_features.json"
with open(fixture_path, "r", encoding="utf-8") as f:
    sample_features = json.load(f)

results = {}

for version in ("fresh", "c7_candidate"):
    print(f"\n{'='*60}")
    print(f"  Benchmarking: {version}")
    print(f"{'='*60}")

    # --- Load time ---
    tracemalloc.start()
    t0 = time.perf_counter()
    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine(model_version=version)
    load_time = time.perf_counter() - t0
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"  Load time:    {load_time:.3f}s")
    print(f"  Peak memory:  {peak_mem / 1024 / 1024:.1f} MiB")

    # --- Inference latency ---
    inf_times = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        engine.predict(sample_features)
        inf_times.append(time.perf_counter() - t0)
    print(f"  Inference:    {mean(inf_times)*1000:.1f}ms avg  (σ={stdev(inf_times)*1000:.1f}ms)")

    # --- SHAP latency ---
    shap_times = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        engine.explain_shap(sample_features)
        shap_times.append(time.perf_counter() - t0)
    print(f"  SHAP:         {mean(shap_times)*1000:.1f}ms avg  (σ={stdev(shap_times)*1000:.1f}ms)")

    results[version] = {
        "load_time_s": round(load_time, 3),
        "peak_memory_mib": round(peak_mem / 1024 / 1024, 1),
        "inference_ms_avg": round(mean(inf_times) * 1000, 1),
        "inference_ms_std": round(stdev(inf_times) * 1000, 1),
        "shap_ms_avg": round(mean(shap_times) * 1000, 1),
        "shap_ms_std": round(stdev(shap_times) * 1000, 1),
    }

    # Force cleanup so the next model loads fresh
    del engine
    import importlib, sentinelai.inference
    importlib.reload(sentinelai.inference)

# --- Summary ---
print(f"\n{'='*60}")
print("  COMPARISON SUMMARY")
print(f"{'='*60}")
print(f"{'Metric':<25} {'Fresh':>12} {'C7':>12} {'Delta':>12}")
print("-" * 61)
for metric, label in [
    ("load_time_s", "Load time (s)"),
    ("peak_memory_mib", "Peak memory (MiB)"),
    ("inference_ms_avg", "Inference (ms)"),
    ("shap_ms_avg", "SHAP (ms)"),
]:
    f_val = results["fresh"][metric]
    c_val = results["c7_candidate"][metric]
    delta = c_val - f_val
    sign = "+" if delta > 0 else ""
    print(f"  {label:<23} {f_val:>12} {c_val:>12} {sign}{delta:>11.1f}")

print("\nC7 model is ~339 MiB vs Fresh ~886 MiB on disk.")
print("If C7 load/inference/SHAP times are comparable or better, it's a clear win.\n")