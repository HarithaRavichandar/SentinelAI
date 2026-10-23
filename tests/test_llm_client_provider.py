# tests/test_llm_client_provider.py
"""Focused unit tests for sentinelai.triage.llm_client._selected_provider.
These tests verify that missing or empty configuration variables cause
LLMConfigurationError to be raised for both Groq and Gemini providers.
"""

import os
import pytest
from sentinelai.triage.llm_client import _selected_provider, LLMConfigurationError

@pytest.fixture(autouse=True)
def restore_env():
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)

def test_selected_provider_groq_missing(monkeypatch):
    os.environ["LLM_PROVIDER"] = "groq"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    with pytest.raises(LLMConfigurationError):
        _selected_provider()
    # Empty strings should also be treated as missing
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GROQ_MODEL"] = ""
    with pytest.raises(LLMConfigurationError):
        _selected_provider()

def test_selected_provider_gemini_missing(monkeypatch):
    os.environ["LLM_PROVIDER"] = "gemini"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(LLMConfigurationError):
        _selected_provider()
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["GEMINI_MODEL"] = ""
    with pytest.raises(LLMConfigurationError):
        _selected_provider()
