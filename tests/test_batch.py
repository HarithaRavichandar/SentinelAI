"""Tests for CSV batch ingestion endpoints.

These tests verify validation, job lifecycle, and that batch predictions match the single
/predict endpoint.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sentinelai.api import app
from sentinelai.inference import InferenceEngine

client = TestClient(app)

# Load a reference feature dict used throughout the tests.
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_features.json"
with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
    SAMPLE_FEATURES: Dict[str, float] = json.load(f)


def _make_csv(rows: List[Dict[str, any]]) -> str:
    """Write *rows* to a temporary CSV file and return the file path.

    The caller is responsible for deleting the file when done.
    """
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


def _upload_csv(file_path: str):
    """Helper to upload a CSV via the FastAPI client."""
    with open(file_path, "rb") as f:
        return client.post("/batch/upload", files={"file": (os.path.basename(file_path), f, "text/csv")})


def test_upload_valid_csv():
    # Create a CSV with two valid rows (duplicate of the fixture).
    rows = [SAMPLE_FEATURES, SAMPLE_FEATURES]
    csv_path = _make_csv(rows)
    try:
        resp = _upload_csv(csv_path)
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
    finally:
        os.unlink(csv_path)


def test_upload_missing_columns():
    # Drop one required column.
    rows = [{k: v for k, v in SAMPLE_FEATURES.items() if k != next(iter(SAMPLE_FEATURES))}]
    csv_path = _make_csv(rows)
    try:
        resp = _upload_csv(csv_path)
        assert resp.status_code == 422
        detail = resp.json().get("detail", {})
        assert isinstance(detail, dict)
        assert "validation_errors" in detail
    finally:
        os.unlink(csv_path)


def test_upload_extra_columns():
    rows = [dict(SAMPLE_FEATURES, **{"ExtraColumn": 1})]
    csv_path = _make_csv(rows)
    try:
        resp = _upload_csv(csv_path)
        assert resp.status_code == 422
        assert "validation_errors" in resp.json().get("detail", {})
    finally:
        os.unlink(csv_path)


def test_upload_non_numeric():
    rows = [dict(SAMPLE_FEATURES, **{next(iter(SAMPLE_FEATURES)): "non-numeric"})]
    csv_path = _make_csv(rows)
    try:
        resp = _upload_csv(csv_path)
        assert resp.status_code == 422
        assert "validation_errors" in resp.json().get("detail", {})
    finally:
        os.unlink(csv_path)


def test_upload_nan_values():
    import numpy as np

    rows = [dict(SAMPLE_FEATURES, **{next(iter(SAMPLE_FEATURES)): np.nan})]
    csv_path = _make_csv(rows)
    try:
        resp = _upload_csv(csv_path)
        assert resp.status_code == 422
        assert "validation_errors" in resp.json().get("detail", {})
    finally:
        os.unlink(csv_path)


def test_upload_empty_csv():
    # CSV with only headers – pandas reads an empty DataFrame.
    df = pd.DataFrame(columns=list(SAMPLE_FEATURES.keys()))
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    df.to_csv(tmp.name, index=False)
    tmp.close()
    try:
        resp = _upload_csv(tmp.name)
        assert resp.status_code == 422
        assert "validation_errors" in resp.json().get("detail", {})
    finally:
        os.unlink(tmp.name)


def test_job_status_progress():
    rows = [SAMPLE_FEATURES]
    csv_path = _make_csv(rows)
    try:
        upload_resp = _upload_csv(csv_path)
        job_id = upload_resp.json()["job_id"]
        status_resp = client.get(f"/batch/{job_id}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["total_rows"] == 1
        assert status_data["processed_rows"] == 1
        assert status_data["status"] == "completed"
    finally:
        os.unlink(csv_path)


def test_job_results_complete():
    rows = [SAMPLE_FEATURES]
    csv_path = _make_csv(rows)
    try:
        upload_resp = _upload_csv(csv_path)
        job_id = upload_resp.json()["job_id"]
        results_resp = client.get(f"/batch/{job_id}/results")
        assert results_resp.status_code == 200
        results = results_resp.json()
        assert results["status"] == "completed"
        assert len(results["results"]) == 1
        res_entry = results["results"][0]
        # Each entry should contain a prediction dict with a class_id.
        assert "prediction" in res_entry
        assert isinstance(res_entry["prediction"].get("class_id"), int)
        # And a triage decision dict.
        assert "decision" in res_entry
    finally:
        os.unlink(csv_path)


def test_job_not_found():
    resp = client.get("/batch/nonexistent-id/status")
    assert resp.status_code == 404


def test_batch_predictions_match_single():
    rows = [SAMPLE_FEATURES]
    csv_path = _make_csv(rows)
    try:
        # Upload batch CSV.
        upload_resp = _upload_csv(csv_path)
        job_id = upload_resp.json()["job_id"]
        results_resp = client.get(f"/batch/{job_id}/results")
        batch_result = results_resp.json()["results"][0]["prediction"]
        # Single predict endpoint.
        single_resp = client.post("/predict", json=SAMPLE_FEATURES)
        assert single_resp.status_code == 200
        single_result = single_resp.json()
        assert batch_result["class_id"] == single_result["class_id"]
    finally:
        os.unlink(csv_path)
