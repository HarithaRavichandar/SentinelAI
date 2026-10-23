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


def test_triage_success():
    payload = load_fixture()
    response = client.post("/triage", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Check core prediction fields
    assert isinstance(data, dict)
    assert "class_id" in data
    assert "class_label" in data
    assert "probabilities" in data
    assert isinstance(data["probabilities"], dict)
    # Check placeholder explanation field
    assert "explanation" in data
    explanation = data["explanation"]
    assert isinstance(explanation, str)
    assert "[Placeholder]" in explanation


def test_triage_invalid_input_returns_400():
    payload = load_fixture()
    # Remove a required feature to trigger validation error
    first_key = next(iter(payload))
    payload.pop(first_key)
    response = client.post("/triage", json=payload)
    assert response.status_code == 400
