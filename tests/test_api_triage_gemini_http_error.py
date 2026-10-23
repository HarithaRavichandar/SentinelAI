import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from sentinelai.api import app
from sentinelai.triage.gemini_client import GeminiHTTPError

client = TestClient(app)

def load_fixture():
    import pathlib, json
    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_triage_fallback_on_gemini_http_error(monkeypatch):
    # Set env vars so Gemini is considered enabled
    monkeypatch.setenv("GEMINI_API_KEY", "valid-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.0-pro")
    payload = load_fixture()
    # Patch get_explanation to raise GeminiHTTPError (e.g., 401 Unauthorized)
    with patch(
        "sentinelai.triage.gemini_client.get_explanation",
        side_effect=GeminiHTTPError(401, {"error": {"message": "Invalid API key"}}),
    ):
        response = client.post("/triage", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Core prediction fields must be present
        for key in ("class_id", "class_label", "probabilities"):
            assert key in data
        # Placeholder should be used
        assert data["explanation_source"] == "placeholder"
        from sentinelai.triage.placeholder import generate_placeholder_explanation
        expected = generate_placeholder_explanation(data)
        assert data["explanation"] == expected
