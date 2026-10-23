# src/sentinelai/triage/llm_client.py
"""Facade for selecting the LLM provider (Gemini or Groq).
The default provider is Groq (controlled by ``LLM_PROVIDER`` env var).
Exports a unified API used by the FastAPI routes.
"""

import os
from typing import Any

# Import Gemini implementation (always available)
from .gemini_client import (
    GeminiConfigurationError as _GeminiConfigError,
    GeminiError as _GeminiError,
    get_explanation as _gemini_explain,
    get_chat_reply as _gemini_chat,
)

# Import Groq implementation (should exist after integration)
from .groq_client import (
    GroqConfigurationError as _GroqConfigError,
    GroqError as _GroqError,
    get_explanation as _groq_explain,
    get_chat_reply as _groq_chat,
)


class LLMConfigurationError(Exception):
    """Raised when the selected provider lacks required configuration."""


class LLMError(Exception):
    """Base class for all provider‑specific runtime errors."""


def _selected_provider() -> str:
    """Select the LLM provider based on the `LLM_PROVIDER` env var.

    Preference order:
    1. Respect explicit `LLM_PROVIDER` (defaults to "groq").
    2. Verify required configuration for the chosen provider.
    3. Raise LLMConfigurationError when the required credentials are missing.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "gemini":
        if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL"):
            return "gemini"
        raise LLMConfigurationError("Gemini provider selected but missing GEMINI_API_KEY or GEMINI_MODEL")
    if provider == "groq":
        if os.getenv("GROQ_API_KEY") and os.getenv("GROQ_MODEL"):
            return "groq"
        raise LLMConfigurationError("Groq provider selected but missing GROQ_API_KEY or GROQ_MODEL")
    raise LLMConfigurationError(f"Unsupported LLM_PROVIDER '{provider}'. Supported: 'gemini', 'groq'.")


def get_explanation(class_id: int, class_label: str, probabilities: Any) -> str:
    """Delegate to the configured provider's ``get_explanation``.

    Raises ``LLMConfigurationError`` if the provider is not configured and
    ``LLMError`` for any provider‑specific runtime error.
    """
    provider = _selected_provider()
    if provider == "gemini":
        try:
            return _gemini_explain(class_id, class_label, probabilities)
        except _GeminiConfigError as exc:
            raise LLMConfigurationError(str(exc)) from exc
        except _GeminiError as exc:
            raise LLMError(str(exc)) from exc
    else:  # default to Groq
        try:
            return _groq_explain(class_id, class_label, probabilities)
        except _GroqConfigError as exc:
            raise LLMConfigurationError(str(exc)) from exc
        except _GroqError as exc:
            raise LLMError(str(exc)) from exc


def get_chat_reply(prompt: str) -> str:
    """Delegate a free‑form chat prompt to the selected provider.

    Mirrors ``get_explanation`` in error handling.
    """
    provider = _selected_provider()
    if provider == "gemini":
        try:
            return _gemini_chat(prompt)
        except _GeminiConfigError as exc:
            raise LLMConfigurationError(str(exc)) from exc
        except _GeminiError as exc:
            raise LLMError(str(exc)) from exc
    else:
        try:
            return _groq_chat(prompt)
        except _GroqConfigError as exc:
            raise LLMConfigurationError(str(exc)) from exc
        except _GroqError as exc:
            raise LLMError(str(exc)) from exc

__all__ = [
    "LLMConfigurationError",
    "LLMError",
    "get_explanation",
    "get_chat_reply",
]
