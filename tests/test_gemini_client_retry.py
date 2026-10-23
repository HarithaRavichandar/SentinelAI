import pytest
import json
from unittest.mock import Mock
import sentinelai.triage.gemini_client as gemini

# Helper to create a fake httpx.Response-like object
class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text
    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise gemini.httpx.HTTPStatusError("status error", request=None, response=self)
    def json(self):
        if self._json is not None:
            return self._json
        raise json.JSONDecodeError("msg", "doc", 0)

# Patch time.sleep to avoid real delays
@pytest.fixture(autouse=True)
def patch_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

def test_retry_success(monkeypatch):
    # Ensure Gemini config is considered enabled for tests
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    # First call returns 503, second call returns 200 with valid payload
    fake_503 = FakeResponse(503, text="service unavailable")
    payload = {"candidates": [{"content": {"parts": [{"text": "Explanation"}]}}]}
    fake_200 = FakeResponse(200, json_data=payload)
    calls = [fake_503, fake_200]
    def fake_post(*args, **kwargs):
        return calls.pop(0)
    monkeypatch.setattr(gemini, "httpx", Mock(post=fake_post))
    explanation = gemini.get_explanation(0, "Benign", {0: 1.0})
    assert explanation == "Explanation"


def test_retry_exhausted(monkeypatch):
    # Ensure Gemini config is considered enabled for tests
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    # All three attempts return 503, leading to GeminiHTTPError
    fake_503 = FakeResponse(503, text="service unavailable")
    calls = [FakeResponse(503, text="service unavailable"), FakeResponse(503, text="service unavailable"), FakeResponse(503, text="service unavailable")]
    def fake_post(*args, **kwargs):
        return calls.pop(0)
    monkeypatch.setattr(gemini, "httpx", Mock(post=fake_post))
    with pytest.raises(gemini.GeminiHTTPError) as exc:
        gemini.get_explanation(0, "Benign", {0: 1.0})
    assert exc.value.status_code == 503


def test_no_retry_on_401(monkeypatch):
    # 401 should raise immediately without retry
    fake_401 = FakeResponse(401, json_data={"error": {"message": "Invalid key"}})
    calls = [fake_401]
    def fake_post(*args, **kwargs):
        return calls.pop(0)
    monkeypatch.setattr(gemini, "httpx", Mock(post=fake_post))
    with pytest.raises(gemini.GeminiHTTPError) as exc:
        gemini.get_explanation(0, "Benign", {0: 1.0})
    assert exc.value.status_code == 401
    # Ensure only one request was made
    assert not calls
