import os
from dotenv import load_dotenv
import logging
from pathlib import Path

# Load environment variables from .env if present; do not override existing OS variables
# Load .env from the repository root (PROJECT_ROOT)
# PROJECT_ROOT is defined later; we will load after its definition
# Placeholder – actual load occurs after PROJECT_ROOT is set
import json
from typing import Literal, Dict, Any

from fastapi import FastAPI, HTTPException
import pathlib
import sys

# Ensure src directory is on sys.path when this module is imported directly (e.g., during tests)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
# Load environment variables from .env located at the project root
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)
# Set up a logger for safe diagnostics
logger = logging.getLogger("sentinelai")
if not os.getenv("GEMINI_API_KEY"):
    logger.warning("Gemini API key not configured (environment variable missing)")
if not os.getenv("GEMINI_MODEL"):
    logger.warning("Gemini model not configured (environment variable missing)")
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
from sentinelai.triage.placeholder import generate_placeholder_explanation
from sentinelai.inference import InferenceEngine, CLASS_MAP
# duplicate placeholder import removed
import sentinelai.triage.llm_client as llm_client

app = FastAPI(title="SentinelAI Inference API", version="1.0.0")

# Initialize a single engine instance at startup – reused for all requests
engine: InferenceEngine | None = None
def get_engine() -> InferenceEngine:
    """Lazily create and return a shared InferenceEngine instance."""
    global engine
    if engine is None:
        engine = InferenceEngine()
    return engine
from pydantic import BaseModel, Field, validator
from typing import List, Optional


class ChatMessage(BaseModel):
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="Message text")

    @validator('role')
    def role_must_be_valid(cls, v):
        if v not in {'user', 'assistant'}:
            raise ValueError("role must be 'user' or 'assistant'")
        return v

    @validator('content')
    def content_not_empty(cls, v):
        if not v.strip():
            raise ValueError('content must not be empty')
        return v


class ChatRequest(BaseModel):
    message: str = Field(..., description="Current user message")
    conversation_history: Optional[List[ChatMessage]] = Field(None, description="Previous messages")

    @validator('message')
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError('message must not be empty')
        if len(v) > 2000:
            raise ValueError('message exceeds maximum length of 2000 characters')
        return v

    @validator('conversation_history')
    def history_limits(cls, v):
        if v is None:
            return v
        if len(v) > 10:
            raise ValueError('conversation_history exceeds maximum 10 messages')
        for msg in v:
            if len(msg.content) > 2000:
                raise ValueError('history message exceeds maximum length of 2000 characters')
        return v


class ChatResponse(BaseModel):
    reply: str
    assistant: Literal["Laya"] = "Laya"
    source: str


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """Interact with the Laya chat assistant.

    Returns a reply generated via the selected LLM provider (controlled by the `LLM_PROVIDER` environment variable).
    If the provider is mis‑configured or encounters an error, a deterministic placeholder response is returned with `source="placeholder"`.
    """
    # Build system prompt and messages for Gemini
    system_prompt = (
        "You are Laya, SentinelAI's security‑triage assistant. "
        "Explain model predictions, discuss suspicious indicators, and recommend safe investigative steps. "
        "Never claim traffic is safe solely because the model predicts Benign, and never invent data or actions not provided."
    )
    # Format conversation history
    history_text = ''
    if request.conversation_history:
        for msg in request.conversation_history:
            prefix = 'User' if msg.role == 'user' else 'Assistant'
            history_text += f"{prefix}: {msg.content}\n"
    # Current user message
    full_prompt = f"{system_prompt}\n{history_text}User: {request.message}\nAssistant:"  # Gemini will continue after Assistant tag
    # Use unified LLM client and determine actual provider via façade
    # Validate provider configuration before invoking the LLM façade
    try:
        provider = llm_client._selected_provider()
    except llm_client.LLMConfigurationError as exc:
        logger.warning("LLM configuration error: %s", exc)
        return ChatResponse(reply="I’m unable to generate a response at this time.", source="placeholder")
    # Call the LLM provider
    try:
        reply = llm_client.get_chat_reply(full_prompt)
        source = provider
    except llm_client.LLMError as exc:
        logger.error("LLM provider error: %s", str(exc))
        reply = "I’m unable to generate a response at this time."
        source = "placeholder"
    except Exception as exc:
        logger.exception("Unexpected error during LLM chat: %s", exc)
        reply = "I’m unable to generate a response at this time."
        source = "placeholder"
    return ChatResponse(reply=reply, source=source)


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Simple health endpoint used by monitoring tools."""
    return {"status": "ok"}

@app.post("/predict")
def predict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run inference on provided features.

    The payload must contain exactly the 76 expected feature keys with finite numeric values.
    Validation errors are returned as HTTP 400 with a clear message.
    """
    try:
        result = get_engine().predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    class_id = result["class_id"]
    if class_id not in CLASS_MAP:
        raise HTTPException(status_code=500, detail="Unknown class_id returned by model")
    result["class_label"] = CLASS_MAP[class_id]
    return result

@app.post("/triage")
def triage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run inference and return an explanation.

    Attempts to obtain an explanation from the Gemini LLM provider. If the
    provider is not configured or fails, a deterministic placeholder explanation
    is returned instead. An ``explanation_source`` field indicates which method
    was used ("gemini" or "placeholder").
    """
    try:
        result = get_engine().predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    class_id = result["class_id"]
    if class_id not in CLASS_MAP:
        raise HTTPException(status_code=500, detail="Unknown class_id returned by model")
    result["class_label"] = CLASS_MAP[class_id]

    # Default to placeholder explanation
    explanation = generate_placeholder_explanation(result)
    source = "placeholder"
    # Validate provider configuration before invoking the LLM façade
    try:
        provider = llm_client._selected_provider()
    except llm_client.LLMConfigurationError as exc:
        logger.warning("LLM configuration error: %s", exc)
        # Return placeholder result early
        result["explanation"] = explanation
        result["explanation_source"] = source
        return result
    # Attempt explanation using the unified LLM client (respecting LLM_PROVIDER)
    try:
        explanation = llm_client.get_explanation(class_id, CLASS_MAP[class_id], result["probabilities"])
        source = provider
    except llm_client.LLMError as exc:
        logger.error("LLM provider error: %s", str(exc))
        # Keep placeholder
    except Exception as exc:
        logger.exception("Unexpected error during LLM explanation: %s", exc)
        # Keep placeholder


    result["explanation"] = explanation
    result["explanation_source"] = source
    return result
