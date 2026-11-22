import json
import pytest
from pathlib import Path
from sentinelai.inference import InferenceEngine


def test_shap_computed():
    """Verify that SHAP explanation is actually computed for the C7 candidate."""
    engine = InferenceEngine(model_version="c7_candidate")

    fixture_path = Path(__file__).parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        features = json.load(f)

    result = engine.explain_shap(features)

    assert result.get("status") != "unavailable", (
        f"SHAP unavailable – fell back with reason: {result.get('reason')}"
    )

    assert "class_id" in result and isinstance(result["class_id"], int)
    assert "shap_explanations" in result and isinstance(result["shap_explanations"], dict)

    shap_explanations = result["shap_explanations"]
    assert len(shap_explanations) == 76

    for val in shap_explanations.values():
        assert isinstance(val, float)
        assert not (val != val or val == float("inf") or val == float("-inf"))

    assert set(shap_explanations.keys()) == set(engine.columns)

    top5 = sorted(shap_explanations.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
    print("Top 5 SHAP features (by absolute value):")
    for name, value in top5:
        print(f"  {name}: {value}")