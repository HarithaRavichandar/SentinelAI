import json
import pathlib

from fastapi.testclient import TestClient

from sentinelai.api import app

client = TestClient(app)


def load_fixture():
    """Load the sample feature fixture used for predictions."""
    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_success():
    payload = load_fixture()
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Basic structure checks
    assert isinstance(data, dict)
    assert "class_id" in data
    assert "class_label" in data
    assert "probabilities" in data
    assert isinstance(data["probabilities"], dict)


def test_missing_feature_returns_400():
    payload = load_fixture()
    # Remove one required feature
    first_key = next(iter(payload))
    payload.pop(first_key)
    response = client.post("/predict", json=payload)
    assert response.status_code == 400


def test_extra_feature_returns_400():
    payload = load_fixture()
    payload["unexpected_feature"] = 0.1
    response = client.post("/predict", json=payload)
    assert response.status_code == 400


def test_non_numeric_and_non_finite_values():
    payload = load_fixture()
    # Non‑numeric value
    first_key = next(iter(payload))
    payload[first_key] = "not-a-number"
    response = client.post("/predict", json=payload)
    assert response.status_code == 400

    # Reset and use NaN
    payload = load_fixture()
    payload[first_key] = float("nan")
    response = client.post("/predict", json=payload)
    assert response.status_code == 400

    # Reset and use infinite
    payload = load_fixture()
    payload[first_key] = float("inf")
    response = client.post("/predict", json=payload)
    assert response.status_code == 400
