import sys
import json
from pathlib import Path
import math

# Resolve project root and add src to Python's import path BEFORE importing sentinelai.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from sentinelai.inference import InferenceEngine, CLASS_MAP


def main():
    fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_features.json"

    if not fixture_path.is_file():
        print(f"Fixture not found: {fixture_path}", file=sys.stderr)
        return 1

    try:
        with fixture_path.open("r", encoding="utf-8") as f:
            sample = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Could not read fixture: {e}", file=sys.stderr)
        return 1

    try:
        engine = InferenceEngine()
        result = engine.predict(sample)
    except Exception as e:
        print(f"Inference failed: {e}", file=sys.stderr)
        return 1

    class_id = result.get("class_id")
    class_label = result.get("class_label")
    probabilities = result.get("probabilities", {})

    if class_id not in CLASS_MAP:
        print(f"Unexpected class ID: {class_id}", file=sys.stderr)
        return 1

    if class_label != CLASS_MAP[class_id]:
        print(
            f"Label mismatch: expected {CLASS_MAP[class_id]}, got {class_label}",
            file=sys.stderr,
        )
        return 1

    if probabilities:
        if not all(
            isinstance(p, (int, float))
            and math.isfinite(p)
            and 0.0 <= p <= 1.0
            for p in probabilities.values()
        ):
            print("Probabilities must be finite values between 0 and 1.", file=sys.stderr)
            return 1

        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-3):
            print(
                f"Probabilities do not sum to 1: {sum(probabilities.values())}",
                file=sys.stderr,
            )
            return 1

    print("Prediction result:")
    print(f"Class ID: {class_id}")
    print(f"Class label: {class_label}")
    print("Probabilities:")

    for cls, prob in probabilities.items():
        print(f"  {cls}: {prob:.4f}")

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())