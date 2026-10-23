# tests/test_provider_selection.py
"""Tests for LLM provider selection consistency across /chat and /triage routes.
All external LLM calls are mocked to avoid network requests.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sentinelai.api import app
from sentinelai.triage.llm_client import LLMConfigurationError, LLMError
import json
from pathlib import Path

client = TestClient(app)

def _load_full_features():
    fixture_path = Path(__file__).parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.fixture(autouse=True)
def restore_env():
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)

def test_chat_uses_groq_when_selected(monkeypatch):
    os.environ["LLM_PROVIDER"] = "groq"
    os.environ["GROQ_API_KEY"] = "dummy"
    os.environ["GROQ_MODEL"] = "dummy"
    monkeypatch.setattr('sentinelai.triage.llm_client.get_chat_reply', lambda prompt: "groq reply")
    response = client.post("/chat", json={"message": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "groq reply"
    assert data["source"] == "groq"

def test_chat_uses_gemini_when_selected(monkeypatch):
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["GEMINI_API_KEY"] = "dummy"
    os.environ["GEMINI_MODEL"] = "dummy"
    monkeypatch.setattr('sentinelai.triage.llm_client.get_chat_reply', lambda prompt: "gemini reply")
    response = client.post("/chat", json={"message": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "gemini reply"
    assert data["source"] == "gemini"

def test_chat_placeholder_on_missing_config(monkeypatch):
    os.environ["LLM_PROVIDER"] = "groq"
    # Ensure GROQ credentials are absent
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setattr('sentinelai.triage.llm_client.get_chat_reply', lambda prompt: "should not be called")
    response = client.post("/chat", json={"message": "test"})
    assert response.status_code == 200
    data = response.json()
    assert data["reply"].startswith("I’m unable")
    assert data["source"] == "placeholder"

def test_triage_uses_groq_explanation(monkeypatch):
    os.environ["LLM_PROVIDER"] = "groq"
    os.environ["GROQ_API_KEY"] = "dummy"
    os.environ["GROQ_MODEL"] = "dummy"
    monkeypatch.setattr('sentinelai.triage.llm_client.get_explanation', lambda cid, label, probs: "groq explanation")
    payload = _load_full_features()
    response = client.post("/triage", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["explanation"] == "groq explanation"
    assert data["explanation_source"] == "groq"

def test_triage_placeholder_on_provider_error(monkeypatch):
    os.environ["LLM_PROVIDER"] = "groq"
    os.environ["GROQ_API_KEY"] = "dummy"
    os.environ["GROQ_MODEL"] = "dummy"
    def raise_error(cid, label, probs):
        raise LLMError("provider failure")
    monkeypatch.setattr('sentinelai.triage.llm_client.get_explanation', raise_error)
    payload = _load_full_features()
    response = client.post("/triage", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["explanation_source"] == "placeholder"
    assert "Unable to generate" in data["explanation"]
