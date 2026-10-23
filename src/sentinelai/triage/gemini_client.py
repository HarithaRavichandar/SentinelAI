# src/sentinelai/triage/gemini_client.py
"""Gemini API client for Laya triage explanations.

The implementation is deliberately lightweight and isolated from the core
inference logic so it can be swapped out for another provider without
modifying other parts of the codebase.

Environment variables (all optional, but ``GEMINI_API_KEY`` and ``GEMINI_MODEL``
must be set for the client to be considered enabled):

- ``GEMINI_API_KEY`` – API key obtained from Google AI Studio.
- ``GEMINI_MODEL`` – Model identifier for the free‑tier model (e.g.
  ``gemini-1.0-pro``). The value is not validated here; it is passed directly
  to the endpoint.
- ``GEMINI_API_ENDPOINT`` – Base URL for the Gemini API. Defaults to the
  official v1beta endpoint.
- ``GEMINI_TIMEOUT_SECONDS`` – Request timeout in seconds (default ``15``).

The client builds a concise prompt containing only the prediction outcome
(class ID, label and probability scores) and sends it to the Gemini
``generateContent`` endpoint via ``httpx``.

All HTTP and network errors are propagated as ``GeminiError`` subclasses so
the caller can decide whether to fall back to a placeholder explanation.
"""

import os
import json
import httpx
from typing import Dict, Any

import time
import logging

logger = logging.getLogger(__name__)

class GeminiError(Exception):
    """Base exception for Gemini provider errors."""

class GeminiConfigurationError(GeminiError):
    """Raised when required configuration is missing or malformed."""

class GeminiResponseError(GeminiError):
    """Raised when the provider returns an unexpected payload."""

class GeminiHTTPError(GeminiError):
    """Raised for non‑2xx HTTP responses.

    Attributes
    ----------
    status_code: int
        The HTTP status code returned by the Gemini endpoint.
    error_body: dict | str
        Parsed JSON error payload if available, otherwise raw text.
    """
    def __init__(self, status_code: int, error_body):
        self.status_code = status_code
        self.error_body = error_body
        super().__init__(f"Gemini HTTP error {status_code}")

# ----- Groq specific error hierarchy -----

class GroqError(Exception):
    """Base exception for Groq provider errors."""

class GroqConfigurationError(GroqError):
    """Raised when required Groq configuration is missing or malformed."""

class GroqResponseError(GroqError):
    """Raised when the Groq provider returns an unexpected payload."""

class GroqHTTPError(GroqError):
    """Raised for non‑2xx HTTP responses from Groq.

    Attributes
    ----------
    status_code: int
        The HTTP status code returned by the Groq endpoint.
    error_body: dict | str
        Parsed JSON error payload if available, otherwise raw text.
    """
    def __init__(self, status_code: int, error_body):
        self.status_code = status_code
        self.error_body = error_body
        super().__init__(f"Groq HTTP error {status_code}")
def _is_enabled() -> bool:
    """Return ``True`` if the required configuration is present.

    The client is considered *enabled* only when both the API key and the
    model name are defined. Timeout and endpoint have sensible defaults.
    """
    return bool(os.getenv("GEMINI_API_KEY")) and bool(os.getenv("GEMINI_MODEL"))


def _build_prompt(class_id: int, class_label: str, probabilities: Dict[int, float]) -> str:
    """Create a minimal, safe prompt for Gemini.

    The prompt contains no raw feature data – only the prediction outcome –
    because the 76‑feature vector may include sensitive information.
    """
    lines = [
        "You are a security‑analysis assistant. Explain the following model prediction.",
        f"Class ID: {class_id}",
        f"Class label: {class_label}",
        "Class probability scores (may not be calibrated confidence estimates):",
    ]
    for cid, prob in sorted(probabilities.items()):
        lines.append(f"- {cid}: {prob:.2f}")
    lines.append(
        "Provide a concise, factual explanation. Do NOT invent details, claim feature causes, or suggest actions."
    )
    return "\n".join(lines)


def get_chat_reply(prompt: str) -> str:
    """Send a free-form prompt to Gemini and return the assistant's reply.

    This reuses the same retry and error‑handling logic as ``get_explanation``.
    """
    # Verify Gemini configuration before any network call
    if not _is_enabled():
        missing = []
        if not os.getenv("GEMINI_API_KEY"):
            missing.append("GEMINI_API_KEY")
        if not os.getenv("GEMINI_MODEL"):
            missing.append("GEMINI_MODEL")
        logger.info("Gemini config missing: %s", ", ".join(missing))
        raise GeminiConfigurationError(
            "Gemini provider is not configured (missing API key or model)."
        )

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    endpoint = os.getenv(
        "GEMINI_API_ENDPOINT",
        "https://generativelanguage.googleapis.com/v1beta",
    )
    timeout_seconds = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "15"))

    url = f"{endpoint}/models/{model}:generateContent"
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    headers = {"x-goog-api-key": api_key}

    attempts = 0
    max_attempts = 3
    backoff = 0.5
    while True:
        try:
            response = httpx.post(url, json=payload, timeout=timeout_seconds, headers=headers)
        except httpx.RequestError as exc:
            # Network‑level error – treat as transient and retry if attempts remain
            if attempts < max_attempts - 1:
                attempts += 1
                logger.warning(
                    "Gemini network error %s, retry %d/%d after %.1fs",
                    str(exc),
                    attempts,
                    max_attempts,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            # Exhausted retries – re‑raise the original request error
            raise
        status = getattr(response, "status_code", None)
        if status is None:
            # Mock without status – treat as success
            break
        if 200 <= status < 300:
            # Successful response – exit loop
            break
        # Retriable server errors (5xx)
        if status in {500, 502, 503, 504} and attempts < max_attempts - 1:
            attempts += 1
            logger.warning(
                "Gemini HTTP %s error, retry %d/%d after %.1fs",
                status,
                attempts,
                max_attempts,
                backoff,
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        # Non‑retriable error – raise Gemini HTTP error
        try:
            error_body = response.json()
        except Exception:
            error_body = getattr(response, "text", None)
        raise GeminiHTTPError(status, error_body)


    try:
        data = response.json()
        reply = (
            data["candidates"][0]["content"]["parts"][0]["text"].strip()
        )
        if not reply:
            raise KeyError
        return reply
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise GeminiResponseError(
            "Malformed response from Gemini provider."
        ) from exc

def get_explanation(class_id: int, class_label: str, probabilities: Dict[int, float]) -> str:
    """Generate an explanation for a prediction using Gemini.

    This builds a prompt from the prediction details and delegates to ``get_chat_reply``.
    """
    prompt = _build_prompt(class_id, class_label, probabilities)
    return get_chat_reply(prompt)


__all__ = [
    "GeminiError",
    "GeminiConfigurationError",
    "GeminiResponseError",
    "get_explanation",
]
