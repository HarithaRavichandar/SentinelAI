# tests/test_model_validation.py
"""Unit tests for the model validation script (scripts/validate_model.py)."""

import json
from pathlib import Path
import tempfile
import joblib
import numpy as np
import pandas as pd
import pytest

from sentinelai.inference import CLASS_MAP
from scripts.validate_model import (
    verify_pipeline_alignment,
    compute_validation_metrics,
    generate_markdown_report,
    PROJECT_ROOT,
)

MODEL_PATH = PROJECT_ROOT / "data" / "models" / "random_forest_balanced.pkl"
PREPROC_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessor_balanced.pkl"


def test_pipeline_alignment_success():
    """Verify that the saved model and preprocessor match feature names and classes."""
    assert MODEL_PATH.is_file(), f"Model file missing: {MODEL_PATH}"
    assert PREPROC_PATH.is_file(), f"Preprocessor file missing: {PREPROC_PATH}"

    model = joblib.load(MODEL_PATH)
    preproc = joblib.load(PREPROC_PATH)
    checks = verify_pipeline_alignment(model, preproc, CLASS_MAP)

    assert checks["passed"] is True
    assert checks["feature_count"] == 76
    assert checks["feature_order_aligned"] is True
    assert checks["classes_aligned"] is True


def test_pipeline_alignment_mismatch_raises():
    """Verify that tampering feature columns or classes triggers ValueError."""
    model = joblib.load(MODEL_PATH)
    preproc = joblib.load(PREPROC_PATH)
    tampered_preproc = {
        "scaler": preproc["scaler"],
        "columns": list(reversed(preproc["columns"])),  # Inverted order
    }

    with pytest.raises(ValueError, match="Pipeline alignment check failed"):
        verify_pipeline_alignment(model, tampered_preproc, CLASS_MAP)


def test_compute_validation_metrics():
    """Test metrics computation and missing class detection with synthetic data."""
    class DummyScaler:
        def transform(self, X):
            return X.values

    class DummyModel:
        classes_ = list(range(10))
        feature_names_in_ = [f"f_{i}" for i in range(5)]

        def predict(self, X):
            # Perfect prediction for class 0, imperfect for others
            return np.array([0, 1, 2, 3, 4])

    columns = [f"f_{i}" for i in range(5)]
    X = pd.DataFrame(np.ones((5, 5)), columns=columns)
    # True labels: classes 0, 1, 2, 3, 4 (classes 5..9 are missing)
    y = np.array([0, 1, 2, 3, 5])

    test_class_map = {i: f"Class_{i}" for i in range(10)}
    metrics = compute_validation_metrics(
        model=DummyModel(),
        scaler=DummyScaler(),
        columns=columns,
        X=X,
        y=y,
        class_map=test_class_map,
    )

    assert "overall_accuracy" in metrics
    assert "balanced_accuracy" in metrics
    assert "macro_f1" in metrics
    assert "weighted_f1" in metrics
    assert "per_class_metrics" in metrics
    assert "confusion_matrix" in metrics
    assert len(metrics["confusion_matrix"]) == 10
    # Classes 4, 6, 7, 8, 9 are missing from y
    missing_ids = [mc["class_id"] for mc in metrics["missing_classes"]]
    assert 6 in missing_ids
    assert 7 in missing_ids
    assert 8 in missing_ids
    assert 9 in missing_ids


def test_report_generation_structure():
    """Verify that markdown report and JSON metrics contain all required sections."""
    meta = {
        "split": "test",
        "mask_file": "test_mask.npy",
        "total_dataset_rows": 100,
        "evaluated_rows": 20,
        "split_proportion": 0.20,
        "disjoint_verified": True,
    }
    pipeline_checks = {
        "feature_count": 76,
        "feature_count_valid": True,
        "feature_order_aligned": True,
        "scaler_aligned": True,
        "model_classes": list(range(10)),
        "classes_aligned": True,
        "passed": True,
    }
    per_class = {}
    for cid, name in CLASS_MAP.items():
        per_class[str(cid)] = {
            "class_id": cid,
            "class_name": name,
            "precision": 0.9,
            "recall": 0.85,
            "f1-score": 0.87,
            "support": 2,
        }
    metrics = {
        "overall_accuracy": 0.85,
        "balanced_accuracy": 0.80,
        "macro_f1": 0.82,
        "weighted_f1": 0.85,
        "inference_latency_seconds": 0.05,
        "latency_per_sample_us": 2500.0,
        "per_class_metrics": per_class,
        "confusion_matrix": np.eye(10, dtype=int).tolist(),
        "missing_classes": [],
        "all_classes_evaluated": True,
    }

    report = generate_markdown_report(
        meta=meta,
        pipeline_checks=pipeline_checks,
        metrics=metrics,
        class_map=CLASS_MAP,
        model_path=MODEL_PATH,
        preproc_path=PREPROC_PATH,
    )

    assert "# SentinelAI - Random Forest Model Validation Report" in report
    assert "## 1. Executive Summary" in report
    assert "## 2. Pipeline Alignment Verification" in report
    assert "## 4. Per-Class Classification Performance" in report
    assert "## 5. Confusion Matrix" in report
    assert "## 6. Evaluation Methodology & Limitations" in report

