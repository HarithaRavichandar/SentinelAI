"""Batch processing module for CSV ingestion and inference.

Provides:
- BatchJob dataclass to track job metadata and progress.
- In‑memory job store (JOB_STORE) mapping job_id (str) → BatchJob.
- validate_csv(file) to load and validate a CSV file against the model's required columns.
- process_batch(job_id, df) to run inference and triage on each row, storing results.

The module is deliberately lightweight and read‑only with respect to the rest
of the application – it does not modify any existing models or storage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Tuple

import pandas as pd
import numpy as np

# In‑memory job registry
JOB_STORE: Dict[str, "BatchJob"] = {}


@dataclass
class BatchJob:
    """Tracks a batch inference job.

    Attributes
    ----------
    job_id: str
        Unique identifier (UUID4 string).
    status: str
        One of "pending", "processing", "completed", "failed".
    total_rows: int
        Number of rows in the uploaded CSV.
    processed_rows: int
        Rows processed so far.
    results: List[Dict[str, Any]]
        Per‑row result dictionaries containing prediction, decision, etc.
    errors: List[str]
        Validation or processing errors.
    created_at: datetime
        Timestamp when the job was created.
    completed_at: datetime | None
        Timestamp when the job finished (or None while running).
    """

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"
    total_rows: int = 0
    processed_rows: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


def _load_engine_columns() -> List[str]:
    """Helper to retrieve the feature column list from the shared engine.

    Import is delayed to avoid circular imports – the FastAPI app creates a
    singleton engine via ``sentinelai.api.get_engine``.
    """
    from sentinelai.api import get_engine

    engine = get_engine()
    # ``engine.columns`` holds the ordered feature names.
    return list(getattr(engine, "columns", []))


def validate_csv(file_path: str) -> Tuple[pd.DataFrame | None, List[str]]:
    """Validate an uploaded CSV file.

    Parameters
    ----------
    file_path: str
        Path to the temporary CSV file on disk.

    Returns
    -------
    tuple(pd.DataFrame | None, List[str])
        A tuple of the validated DataFrame (or ``None`` on fatal error) and a
        list of validation error messages.
    """
    errors: List[str] = []
    try:
        df = pd.read_csv(file_path)
    except Exception as exc:
        errors.append(f"Failed to read CSV: {exc}")
        return None, errors

    # Empty CSV check (headers only, no data rows)
    if df.empty:
        errors.append("CSV contains no data rows (empty).")
        return None, errors

    required_cols = _load_engine_columns()
    if not required_cols:
        errors.append("Engine feature columns could not be determined.")
        return None, errors

    # Column presence
    missing = set(required_cols) - set(df.columns)
    extra = set(df.columns) - set(required_cols)
    if missing:
        errors.append(f"Missing required columns: {sorted(missing)}")
    if extra:
        errors.append(f"Unexpected extra columns: {sorted(extra)}")

    # Numeric & finite validation (skip if column errors already found)
    if not errors:
        # Ensure all columns are numeric
        non_numeric = []
        for col in required_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                non_numeric.append(col)
        if non_numeric:
            errors.append(f"Columns not numeric: {non_numeric}")
        if not non_numeric:
            # Only check NaN/Inf when all columns are confirmed numeric
            if df[required_cols].isnull().any().any():
                errors.append("CSV contains missing (NaN) values.")
            elif not np.isfinite(df[required_cols].values.astype(float)).all():
                errors.append("CSV contains non‑finite (Inf) values.")

    return (df if not errors else None), errors


def process_batch(job_id: str, df: pd.DataFrame) -> None:
    """Process a validated DataFrame row‑by‑row.

    Updates the global ``JOB_STORE`` entry for ``job_id`` with progress and
    per‑row results. Exceptions are captured and the job status is set to
    ``failed``.
    """
    job = JOB_STORE.get(job_id)
    if not job:
        # Defensive: job should exist, but abort silently if not.
        return

    job.status = "processing"
    job.total_rows = len(df)
    job.processed_rows = 0
    job.results = []
    job.errors = []

    from sentinelai.api import get_engine
    from sentinelai.triage.decision_engine import evaluate_triage_decision

    engine = get_engine()

    try:
        for _, row in df.iterrows():
            # Convert row to dict matching feature names
            row_dict = row.to_dict()
            # Prediction
            try:
                pred = engine.predict(row_dict)
            except Exception as exc:
                job.errors.append(f"Prediction error on row {_}: {exc}")
                continue

            # Triage decision (uses the same prediction contract as the API)
            try:
                decision = evaluate_triage_decision(pred)
            except Exception as exc:
                job.errors.append(f"Decision error on row {_}: {exc}")
                decision = None

            result_entry: Dict[str, Any] = {
                "features": row_dict,
                "prediction": pred,
                "decision": decision,
            }
            job.results.append(result_entry)
            job.processed_rows += 1
    except Exception as exc:
        job.status = "failed"
        job.errors.append(f"Batch processing aborted: {exc}")
        job.completed_at = datetime.utcnow()
        return

    job.status = "completed"
    job.completed_at = datetime.utcnow()