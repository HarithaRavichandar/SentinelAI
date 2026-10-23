# tests/test_api_triage_gemini.py
"""Integration tests for the /triage endpoint with a mocked Gemini provider.
These tests verify that:
- When Gemini is configured and returns an explanation, the response contains
  "explanation_source": "gemini" and the returned explanation.
- When Gemini fails (e.g., raises an exception), the endpoint falls back to the
  placeholder explanation and sets "explanation_source": "placeholder" while
  preserving the prediction fields.
All network calls are mocked; no real Gemini API access occurs.
"""

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from sentinelai.api import app
from sentinelai.triage.placeholder import generate_placeholder_explanation

client = TestClient(app)

def load_fixture():
    import pathlib, json
    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    # Ensure Gemini looks enabled for the success test; leave disabled for others.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.0-pro")

def test_triage_success_uses_gemini(monkeypatch):
    # Patch the Gemini client to return a deterministic explanation.
    mock_explanation = "Gemini generated explanation."
    with patch("sentinelai.api.get_explanation", return_value=mock_explanation) as mock_get:
        payload = load_fixture()
        response = client.post("/triage", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Core prediction fields must be present
        for key in ("class_id", "class_label", "probabilities"):
            assert key in data
        # Gemini specific fields
        assert data["explanation"] == mock_explanation
        assert data["explanation_source"] == "gemini"
        # Ensure the Gemini client was called with correct arguments
        mock_get.assert_called_once()
        args, _ = mock_get.call_args
        class_id, class_label, probs = args
        assert isinstance(class_id, int)
        assert isinstance(class_label, str)
        assert isinstance(probs, dict)

def test_triage_fallback_to_placeholder(monkeypatch):
    # Simulate Gemini raising a configuration error (e.g., missing API key)
    with patch("sentinelai.triage.gemini_client.get_explanation", side_effect=Exception("boom")):
        # Clear env to make Gemini think it's disabled
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        payload = load_fixture()
        response = client.post("/triage", json=payload)
        assert response.status_code == 200
        data = response.json()
        # Core prediction fields must be present
        for key in ("class_id", "class_label", "probabilities"):
            assert key in data
        # Placeholder explanation must be used
        placeholder = generate_placeholder_explanation(data)
        assert data["explanation"] == placeholder
        assert data["explanation_source"] == "placeholder"
