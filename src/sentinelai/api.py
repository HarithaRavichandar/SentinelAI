import os
from dotenv import load_dotenv
import logging
from pathlib import Path
from sentinelai.capture.api_routes import router as capture_router

# Load environment variables from .env if present; do not override existing OS variables
# Load .env from the repository root (PROJECT_ROOT)
# PROJECT_ROOT is defined later; we will load after its definition
# Placeholder – actual load occurs after PROJECT_ROOT is set
import json
from typing import Literal, Dict, Any

from fastapi import FastAPI, HTTPException, Query
import pathlib
import sys
import time
import csv, random

# Ensure src directory is on sys.path when this module is imported directly (e.g., during tests)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
# Load environment variables from .env located at the project root
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)
# Set up a logger for safe diagnostics
logger = logging.getLogger("sentinelai")
CLASS_MAP: Dict[int, str] = {
    0: "Benign",
    1: "Analysis",
    2: "Backdoor",
    3: "DoS",
    4: "Exploits",
    5: "Fuzzers",
    6: "Generic",
    7: "Reconnaissance",
    8: "Shellcode",
    9: "Worms",
}
if not os.getenv("GEMINI_API_KEY"):
    logger.warning("Gemini API key not configured (environment variable missing)")
if not os.getenv("GEMINI_MODEL"):
    logger.warning("Gemini model not configured (environment variable missing)")
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
from sentinelai.triage.placeholder import (
    generate_placeholder_explanation,
    build_explanation_provenance,
    EXPLANATION_SOURCE_TEMPLATE,
)
from sentinelai.triage import llm_client
from sentinelai.triage.decision_engine import evaluate_triage_decision, TriageDecision
from sentinelai.storage import insert_alert, get_alerts, init_db
from sentinelai.storage.db import update_alert_status

try:
    init_db()
except Exception as exc:
    logger.warning("Failed to initialize alerts database: %s", exc)

# Simple wrapper so tests can patch sentinelai.api.get_explanation

# ---------------------------------------------------------------------------
# Batch processing imports
# ---------------------------------------------------------------------------
from fastapi import UploadFile, File, HTTPException
from pydantic import BaseModel
from sentinelai.batch import (
    BatchJob,
    JOB_STORE,
    validate_csv,
    process_batch,
)

class BatchUploadResponse(BaseModel):
    job_id: str
    detail: str = "Batch job created and processing started"

class BatchStatusResponse(BaseModel):
    job_id: str
    status: str
    total_rows: int
    processed_rows: int

class BatchResultsResponse(BaseModel):
    job_id: str
    status: str
    results: list
    errors: list = []

class AlertStatusUpdate(BaseModel):
    """Request body for updating an alert's workflow status."""
    alert_status: Literal["new", "acknowledged", "investigating", "resolved", "false_positive"]

# Simple wrapper so tests can patch sentinelai.api.get_explanation
def get_explanation(class_id: int, class_label: str, probabilities: Any) -> str:
    """Delegate to the LLM client façade.

    This wrapper exists to keep backward‑compatible import paths used in the test
    suite (e.g., ``patch('sentinelai.api.get_explanation')``). It forwards the call
    to ``llm_client.get_explanation`` which implements the provider selection
    logic.
    """
    return llm_client.get_explanation(class_id, class_label, probabilities)



app = FastAPI(title="SentinelAI Inference API", version="1.0.0")
app.include_router(capture_router)

# ---- CORS configuration for local development ----
from fastapi.middleware.cors import CORSMiddleware

# Allow the Vite dev server origins only
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize a single engine instance at startup – reused for all requests
engine: Any | None = None
def get_engine() -> Any:
    """Lazily import InferenceEngine and CLASS_MAP and create shared instance."""
    global engine
    if engine is None:
        from sentinelai.inference import InferenceEngine, CLASS_MAP
        engine = InferenceEngine()
        # expose CLASS_MAP at module level for later use
        globals()['CLASS_MAP'] = CLASS_MAP
    return engine


def reset_engine() -> None:
    """Reset cached engine instance (useful when switching model versions in tests)."""
    global engine
    engine = None
from pydantic import BaseModel, Field, validator, field_validator
from typing import List, Optional


class ChatMessage(BaseModel):
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="Message text")

    @field_validator('role')
    def role_must_be_valid(cls, v):
        if v not in {'user', 'assistant'}:
            raise ValueError("role must be 'user' or 'assistant'")
        return v

    @field_validator('content')
    def content_not_empty(cls, v):
        if not v.strip():
            raise ValueError('content must not be empty')
        return v


class ChatRequest(BaseModel):
    message: str = Field(..., description="Current user message")
    conversation_history: Optional[List[ChatMessage]] = Field(None, description="Previous messages")

    @field_validator('message')
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError('message must not be empty')
        if len(v) > 2000:
            raise ValueError('message exceeds maximum length of 2000 characters')
        return v

    @field_validator('conversation_history')
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
    provenance: Optional[Dict[str, Any]] = None


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """Interact with the Laya chat assistant.

    Returns a reply generated via the selected LLM provider (controlled by the `LLM_PROVIDER` environment variable).
    If the provider is misconfigured or encounters an error, a deterministic template response is returned with `source="template"`.
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
        prov = build_explanation_provenance(EXPLANATION_SOURCE_TEMPLATE)
        return ChatResponse(
            reply="I'm unable to generate a response at this time.",
            source=EXPLANATION_SOURCE_TEMPLATE,
            provenance=prov,
        )
    # Call the LLM provider
    try:
        reply = llm_client.get_chat_reply(full_prompt)
        source = provider
    except llm_client.LLMError as exc:
        logger.error("LLM provider error: %s", str(exc))
        reply = "I'm unable to generate a response at this time."
        source = EXPLANATION_SOURCE_TEMPLATE
    except Exception as exc:
        logger.exception("Unexpected error during LLM chat: %s", exc)
        reply = "I'm unable to generate a response at this time."
        source = EXPLANATION_SOURCE_TEMPLATE

    prov = build_explanation_provenance(source)
    return ChatResponse(reply=reply, source=source, provenance=prov)


@app.get("/health")
def health_check(model_info: bool = False) -> Dict[str, Any]:
    """Simple health endpoint used by monitoring tools.

    By default returns {"status": "ok"} to preserve existing API response contracts.
    If model_info=True, returns active model_version alongside status.
    """
    res = {"status": "ok"}
    if model_info:
        eng = get_engine()
        res["model_version"] = getattr(eng, "model_version", "legacy")
    return res


@app.get("/status")
def status_info() -> Dict[str, Any]:
    """Status endpoint exposing system health, active model version, and artifact configuration."""
    eng = get_engine()
    return {
        "status": "ok",
        "model_version": getattr(eng, "model_version", "legacy"),
        "model_path": str(getattr(eng, "model_path", "")),
        "columns_count": len(getattr(eng, "columns", [])),
    }

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

# ------------------------------------------------------------------
# Sample endpoint for demo purposes – returns one random row with label.
# ------------------------------------------------------------------

_SAMPLE_CACHE: Optional[Dict[int, List[Dict[str, Any]]]] = None


def _resolve_label(label_str: str) -> Optional[int]:
    """Resolve a class label name or string numeric ID to its integer class ID."""
    cleaned = label_str.strip().lower()
    try:
        cid = int(cleaned)
        if cid in CLASS_MAP:
            return cid
    except ValueError:
        pass
    for cid, name in CLASS_MAP.items():
        if name.lower() == cleaned:
            return cid
    return None


def _get_sample_pool(samples_per_class: int = 30) -> Dict[int, List[Dict[str, Any]]]:
    """Load a stratified pool of samples from the raw dataset, cached in memory by class_id."""
    global _SAMPLE_CACHE
    if _SAMPLE_CACHE is not None:
        return _SAMPLE_CACHE

    data_path = PROJECT_ROOT / "data" / "raw" / "Data.csv"
    label_path = PROJECT_ROOT / "data" / "raw" / "Label.csv"

    if not data_path.exists() or not label_path.exists():
        raise HTTPException(status_code=500, detail="Dataset files missing or empty")

    collected: Dict[int, List[Dict[str, Any]]] = {cid: [] for cid in CLASS_MAP}
    needed_classes = set(CLASS_MAP.keys())

    with open(data_path, newline="") as f_data, open(label_path, newline="") as f_label:
        data_reader = csv.DictReader(f_data)
        label_reader = csv.DictReader(f_label)
        for row, label_row in zip(data_reader, label_reader):
            label_col = next((c for c in label_row if c.lower() == "label"), None)
            raw_val = label_row.get(label_col) if label_col else next(iter(label_row.values()))
            try:
                cid = int(raw_val)
            except (ValueError, TypeError):
                continue

            if cid in collected and len(collected[cid]) < samples_per_class:
                parsed_features = {}
                for k, v in row.items():
                    try:
                        parsed_features[k] = float(v)
                    except ValueError:
                        parsed_features[k] = v
                collected[cid].append(parsed_features)

                # Stop early once we have enough samples for all classes
                if all(len(collected[c]) >= samples_per_class for c in needed_classes):
                    break

    if not any(collected.values()):
        raise HTTPException(status_code=500, detail="Dataset files missing or empty")

    _SAMPLE_CACHE = collected
    return _SAMPLE_CACHE


@app.get("/sample")
def get_sample(label: Optional[str] = Query(None, description="Optional class label or numeric ID")) -> dict:
    """Return a single real sample from the raw dataset.

    Parameters:
        label: Optional class name (e.g. 'DoS', 'Benign') or numeric ID (e.g. '3').
               If omitted, selects randomly across available classes.

    Response format:
        {"features": {feature_name: value, ...}, "label": "<class name>"}
    The features dict follows the exact column order expected by the model.
    """
    pool = _get_sample_pool()

    if label is not None and label.strip():
        cid = _resolve_label(label)
        if cid is None:
            supported = ", ".join(CLASS_MAP[c] for c in sorted(CLASS_MAP.keys()))
            raise HTTPException(
                status_code=400,
                detail=f"Invalid label '{label}'. Supported classes: {supported}",
            )
        class_samples = pool.get(cid, [])
        if not class_samples:
            raise HTTPException(
                status_code=404,
                detail=f"No samples available for class '{CLASS_MAP[cid]}'",
            )
        chosen_sample = random.choice(class_samples)
        return {"features": dict(chosen_sample), "label": CLASS_MAP[cid]}

    # No label specified: pick uniformly from classes that have samples
    available_classes = [cid for cid, samples in pool.items() if samples]
    if not available_classes:
        raise HTTPException(status_code=500, detail="Dataset files missing or empty")

    chosen_cid = random.choice(available_classes)
    chosen_sample = random.choice(pool[chosen_cid])
    return {"features": dict(chosen_sample), "label": CLASS_MAP[chosen_cid]}

@app.post("/triage")
def triage(payload: Dict[str, Any], explain_shap: bool = Query(False)) -> Dict[str, Any]:
    """Run prediction and return optional explanations.

    Steps:
    1. Predict using engine.
    2. Add class_label.
    3. Get LLM explanation via get_explanation (fallback to placeholder).
    4. If explain_shap=True, compute SHAP contributions.
    5. Include timing logs for each step.
    """
    # 0. Diagnostic logging for explain_shap flag
    logger.info(f"/triage called – explain_shap={explain_shap}")

    # 1. Prediction (unchanged)
    start_pred = time.time()
    try:
        result = get_engine().predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    pred_time = time.time() - start_pred
    logger.info(f"Prediction time: {pred_time:.3f}s")

    class_id = result["class_id"]
    if class_id not in CLASS_MAP:
        raise HTTPException(status_code=500, detail="Unknown class_id returned by model")
    result["class_label"] = CLASS_MAP[class_id]

    # 2. Explanation
    start_exp = time.time()
    try:
        provider = llm_client._selected_provider()
        explanation = get_explanation(class_id, result["class_label"], result.get("probabilities", {}))
        explanation_source = provider
    except Exception:
        explanation = generate_placeholder_explanation(result)
        explanation_source = EXPLANATION_SOURCE_TEMPLATE
    exp_time = time.time() - start_exp
    logger.info(f"Explanation time: {exp_time:.3f}s")
    result["explanation"] = explanation
    result["explanation_source"] = explanation_source
    result["explanation_provenance"] = build_explanation_provenance(explanation_source)

    # 3. Optional SHAP with detailed logging
    if explain_shap:
        logger.info("Entering SHAP computation block")
        try:
            start_shap = time.time()
            shap_result = get_engine().explain_shap(payload)
            shap_time = time.time() - start_shap
            logger.info(f"SHAP computation time: {shap_time:.3f}s")
            logger.info(f"SHAP result keys: {list(shap_result.keys())}")
        except Exception as exc:
            logger.exception("Unexpected error during SHAP computation")
            shap_result = {"status": "unavailable", "reason": str(exc)}
        # Normalize SHAP result keys
        if isinstance(shap_result, dict):
            if "status" in shap_result:
                shap_result["shap_status"] = shap_result.pop("status")
            if "reason" in shap_result:
                shap_result["shap_reason"] = shap_result.pop("reason")
            result.update(shap_result)
        else:
            result["shap"] = shap_result

    # 4. Structured Triage Decision (Laya decision engine)
    start_decision = time.time()
    try:
        shap_explanations = (
            result.get("shap_explanations")
            if isinstance(result.get("shap_explanations"), dict)
            else None
        )
        decision = evaluate_triage_decision(
            prediction=result,
            shap_result=shap_explanations,
            raw_features=payload,
        )
        result["decision"] = decision.model_dump(mode="json")
    except Exception as exc:
        logger.exception("Unexpected error during triage decision evaluation: %s", exc)
        result["decision"] = {
            "predicted_class": result.get("class_label", "Unknown"),
            "priority": "review_required",
            "recommended_action": "escalate_to_tier2_analyst",
            "decision_confidence": 0.0,
            "decision_status": "unavailable",
            "evidence": ["Error evaluating automated triage decision."],
            "uncertainty_reasons": [str(exc)],
            "requires_human_review": True,
            "policy_mode": None,
        }
    decision_time = time.time() - start_decision
    logger.info(f"Decision evaluation time: {decision_time:.3f}s")

    # 5. Persist successful triage result (without raw network payload features)
    total_latency_ms = round((time.time() - start_pred) * 1000, 1)
    result["latencyMs"] = total_latency_ms
    try:
        alert_id = insert_alert(
            class_id=result["class_id"],
            class_label=result["class_label"],
            probabilities=result["probabilities"],
            latency_ms=total_latency_ms,
            decision=result.get("decision"),
            explanation=result.get("explanation"),
            explanation_source=result.get("explanation_source"),
        )
        if alert_id is not None:
            result["id"] = alert_id
    except Exception as exc:
        logger.warning("Failed to persist triage alert to database: %s", exc)

    # 6. Final response
    return result


@app.get("/alerts")
def list_alerts(limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
    """Retrieve recent triaged alerts in descending chronological order."""
    try:
        return get_alerts(limit=limit)
    except Exception as exc:
        logger.exception("Error listing alerts: %s", exc)
        return []


@app.patch("/api/alerts/{alert_id}/status")
def patch_alert_status(alert_id: int, body: AlertStatusUpdate) -> Dict[str, Any]:
    """Update the workflow status of an alert (new → acknowledged → investigating → resolved/false_positive)."""
    updated = update_alert_status(alert_id, body.alert_status)
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"id": alert_id, "alert_status": body.alert_status}


@app.post("/decision")
def get_decision(payload: Dict[str, Any], explain_shap: bool = Query(False)) -> Dict[str, Any]:
    """Run prediction and return structured cybersecurity triage decision directly."""
    triage_res = triage(payload, explain_shap=explain_shap)
    return triage_res["decision"]

# ---------------------------------------------------------------------------
# Batch endpoints
# ---------------------------------------------------------------------------

@app.post("/batch/upload", response_model=BatchUploadResponse)
async def batch_upload(file: UploadFile = File(...)) -> BatchUploadResponse:
    """Upload a CSV for batch processing.

    The file is validated against the model's feature columns. A job is created
    and processing starts synchronously (suitable for test environments)."""
    # Save uploaded file to a temporary location for pandas to read.
    import tempfile, os
    try:
        suffix = os.path.splitext(file.filename)[1] or ".csv"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        df, validation_errors = validate_csv(tmp_path)
    finally:
        # Ensure temporary file is removed.
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if validation_errors:
        raise HTTPException(status_code=422, detail={"validation_errors": validation_errors})

    if df is None:
        raise HTTPException(status_code=400, detail="CSV validation failed")

    job = BatchJob()
    JOB_STORE[job.job_id] = job
    # Process synchronously – for large files this could be async/background.
    process_batch(job.job_id, df)
    return BatchUploadResponse(job_id=job.job_id)

@app.get("/batch/{job_id}/status", response_model=BatchStatusResponse)
def batch_status(job_id: str) -> BatchStatusResponse:
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return BatchStatusResponse(
        job_id=job.job_id,
        status=job.status,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
    )

@app.get("/batch/{job_id}/results", response_model=BatchResultsResponse)
def batch_results(job_id: str) -> BatchResultsResponse:
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    if job.status != "completed":
        raise HTTPException(status_code=202, detail="Batch job still processing")
    return BatchResultsResponse(
        job_id=job.job_id,
        status=job.status,
        results=job.results,
        errors=job.errors,
    )