# src/sentinelai/triage/groq_client.py
"""Groq API client for Laya triage explanations.
Implements the same interface as :pymod:`gemini_client` so the rest of the
application can treat both providers uniformly.
"""

import os
import json
import httpx
import time
import logging
from typing import Dict

from .prompt_builder import build_prompt

logger = logging.getLogger(__name__)

# --- Exception hierarchy (mirrors Gemini equivalents) ---

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
    """Return ``True`` if the required Groq configuration is present.

    Both ``GROQ_API_KEY`` and ``GROQ_MODEL`` must be defined for the client to be
    considered enabled. ``GROQ_TIMEOUT_SECONDS`` has a sensible default.
    """
    return bool(os.getenv("GROQ_API_KEY")) and bool(os.getenv("GROQ_MODEL"))


def get_chat_reply(prompt: str) -> str:
    """Send a free‑form prompt to Groq and return the assistant's reply.

    The function mirrors :func:`gemini_client.get_chat_reply` – it validates the
    configuration, performs a bounded retry loop for transient failures and
    raises the appropriate ``Groq*`` exceptions for callers to handle.
    """
    if not _is_enabled():
        missing = []
        if not os.getenv("GROQ_API_KEY"):
            missing.append("GROQ_API_KEY")
        if not os.getenv("GROQ_MODEL"):
            missing.append("GROQ_MODEL")
        logger.info("Groq config missing: %s", ", ".join(missing))
        raise GroqConfigurationError(
            "Groq provider is not configured (missing API key or model)."
        )

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL")
    endpoint = os.getenv("GROQ_API_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions")
    timeout_seconds = int(os.getenv("GROQ_TIMEOUT_SECONDS", "15"))

    url = endpoint
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are Laya, a security‑analysis assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }

    attempts = 0
    max_attempts = 3
    backoff = 0.5
    while True:
        try:
            response = httpx.post(url, json=payload, timeout=timeout_seconds, headers=headers)
        except httpx.RequestError as exc:
            if attempts < max_attempts - 1:
                attempts += 1
                logger.warning(
                    "Groq network error %s, retry %d/%d after %.1fs",
                    str(exc), attempts, max_attempts, backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            raise

        status = getattr(response, "status_code", None)
        if status is None:
            break
        if 200 <= status < 300:
            break
        if status in {401, 403, 400, 429}:
            try:
                error_body = response.json()
            except Exception:
                error_body = getattr(response, "text", None)
            raise GroqHTTPError(status, error_body)
        if status in {500, 502, 503, 504} and attempts < max_attempts - 1:
            attempts += 1
            logger.warning(
                "Groq HTTP %s error, retry %d/%d after %.1fs",
                status, attempts, max_attempts, backoff,
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        try:
            error_body = response.json()
        except Exception:
            error_body = getattr(response, "text", None)
        raise GroqHTTPError(status, error_body)

    try:
        data = response.json()
        reply = data["choices"][0]["message"]["content"].strip()
        if not reply:
            raise KeyError
        return reply
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise GroqResponseError("Malformed response from Groq provider.") from exc


def get_explanation(class_id: int, class_label: str, probabilities: Dict[int, float]) -> str:
    """Generate an explanation for a prediction using Groq.

    The prompt is built with :func:`prompt_builder.build_prompt` to keep the two
    providers consistent.
    """
    prompt = build_prompt(class_id, class_label, probabilities)
    return get_chat_reply(prompt)


__all__ = [
    "GroqError",
    "GroqConfigurationError",
    "GroqResponseError",
    "GroqHTTPError",
    "get_explanation",
    "get_chat_reply",
]
