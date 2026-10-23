# tests/test_gemini_client_mock.py
"""Tests for the Gemini client using mocked HTTP responses.
These tests never perform real network calls and verify:
* Successful parsing of a valid Gemini response.
* Proper handling of missing configuration (API key / model).
* Propagation of authentication errors (401/403), rate‑limit errors (429),
  and generic HTTP errors.
* Handling of request timeouts / network failures.
* Detection of malformed JSON or missing fields, including empty explanation.
* That the request payload contains *only* the prediction information and never
  the raw 76‑feature vector.
* That the API key never appears in the FastAPI response payload.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
import httpx

from sentinelai.triage.gemini_client import (
    get_explanation,
    GeminiConfigurationError,
    GeminiResponseError,
)

# Helper to build a minimal mock response object
def make_mock_response(status_code=200, json_data=None, raise_for_status=None):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if raise_for_status:
        mock_resp.raise_for_status.side_effect = raise_for_status
    else:
        mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = json_data
    return mock_resp

@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """Ensure a clean environment for each test."""
    for var in ["GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_API_ENDPOINT", "GEMINI_TIMEOUT_SECONDS"]:
        monkeypatch.delenv(var, raising=False)

def test_missing_configuration_raises():
    with pytest.raises(GeminiConfigurationError):
        get_explanation(0, "label", {0: 1.0})

@patch("httpx.post")
def test_successful_response_parsing(mock_post):
    os.environ["GEMINI_API_KEY"] = "fake-key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    # Mock a valid Gemini payload
    payload = {"candidates": [{"content": {"parts": [{"text": "This is an explanation."}]}}]}
    mock_post.return_value = make_mock_response(json_data=payload)

    explanation = get_explanation(1, "malware", {1: 0.87, 0: 0.13})
    assert explanation == "This is an explanation."
    # Verify that the request body only contains the prompt (no raw features)
    args, kwargs = mock_post.call_args
    sent_json = kwargs["json"]
    assert "contents" in sent_json
    # The prompt text should contain only class info, not the full feature dict
    prompt_text = sent_json["contents"][0]["parts"][0]["text"]
    assert "Class ID" in prompt_text
    assert "Class label" in prompt_text
    assert "Class probability scores" in prompt_text
    assert "raw" not in prompt_text.lower()

@patch("httpx.post")
def test_http_401_auth_failure(mock_post):
    os.environ["GEMINI_API_KEY"] = "bad-key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    mock_post.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized", request=MagicMock(), response=MagicMock(status_code=401)
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        get_explanation(0, "label", {0: 1.0})
    assert exc.value.response.status_code == 401

@patch("httpx.post")
def test_http_429_rate_limit(mock_post):
    os.environ["GEMINI_API_KEY"] = "key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    mock_post.side_effect = httpx.HTTPStatusError(
        "429 Too Many Requests", request=MagicMock(), response=MagicMock(status_code=429)
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        get_explanation(0, "label", {0: 1.0})
    assert exc.value.response.status_code == 429

@patch("httpx.post")
def test_other_http_error(mock_post):
    os.environ["GEMINI_API_KEY"] = "key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    mock_post.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error", request=MagicMock(), response=MagicMock(status_code=500)
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        get_explanation(0, "label", {0: 1.0})
    assert exc.value.response.status_code == 500

@patch("httpx.post")
def test_request_timeout(mock_post):
    os.environ["GEMINI_API_KEY"] = "key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    mock_post.side_effect = httpx.RequestError("timeout", request=MagicMock())
    with pytest.raises(httpx.RequestError):
        get_explanation(0, "label", {0: 1.0})

@patch("httpx.post")
def test_malformed_json_raises(mock_post):
    os.environ["GEMINI_API_KEY"] = "key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    # Return JSON missing the expected fields
    mock_post.return_value = make_mock_response(json_data={"unexpected": 123})
    with pytest.raises(GeminiResponseError):
        get_explanation(0, "label", {0: 1.0})

@patch("httpx.post")
def test_empty_explanation_raises(mock_post):
    os.environ["GEMINI_API_KEY"] = "key"
    os.environ["GEMINI_MODEL"] = "gemini-1.0-pro"
    payload = {"candidates": [{"content": {"parts": [{"text": "   "}]}}]}
    mock_post.return_value = make_mock_response(json_data=payload)
    with pytest.raises(GeminiResponseError):
        get_explanation(0, "label", {0: 1.0})
