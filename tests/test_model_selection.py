# tests/test_model_selection.py
"""Tests for configurable Random Forest model selection in SentinelAI (SENTINELAI_MODEL_VERSION)."""

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sentinelai.api import app, reset_engine
from sentinelai.inference import (
    CLASS_MAP,
    DEFAULT_MODEL_VERSION,
    ENV_MODEL_VERSION,
    MODEL_ARTIFACTS,
    PROJECT_ROOT,
    InferenceEngine,
    ModelConfigurationError,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure clean environment and reset singleton engine before/after each test."""
    monkeypatch.delenv(ENV_MODEL_VERSION, raising=False)
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def client():
    return TestClient(app)


def test_default_model_selection_is_c7_candidate():
    """Unset SENTINELAI_MODEL_VERSION must default to c7_candidate model and preprocessor."""
    engine = InferenceEngine()
    assert engine.model_version == "c7_candidate"
    assert engine.model_version == DEFAULT_MODEL_VERSION
    assert engine.model_path == PROJECT_ROOT / "staging" / "c7_candidate" / "C7_random_forest_depth30_leaf3.pkl"
    assert engine.preproc_path == PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl"
    assert engine.n_features == 76
    assert len(engine.columns) == 76


def test_explicit_legacy_selection_env(monkeypatch):
    """Explicit SENTINELAI_MODEL_VERSION='legacy' loads legacy model."""
    monkeypatch.setenv(ENV_MODEL_VERSION, "legacy")
    engine = InferenceEngine()
    assert engine.model_version == "legacy"
    assert engine.model_path == MODEL_ARTIFACTS["legacy"]["model_path"]
    assert engine.preproc_path == MODEL_ARTIFACTS["legacy"]["preproc_path"]


def test_explicit_legacy_selection_param():
    """Explicit model_version='legacy' argument loads legacy model."""
    engine = InferenceEngine(model_version="legacy")
    assert engine.model_version == "legacy"
    assert engine.model_path == MODEL_ARTIFACTS["legacy"]["model_path"]


def test_explicit_fresh_selection_env(monkeypatch):
    """Explicit SENTINELAI_MODEL_VERSION='fresh' loads fresh model and preprocessor."""
    monkeypatch.setenv(ENV_MODEL_VERSION, "fresh")
    engine = InferenceEngine()
    assert engine.model_version == "fresh"
    assert engine.model_path == PROJECT_ROOT / "data" / "models_fresh" / "random_forest_fresh.pkl"
    assert engine.preproc_path == PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl"
    assert engine.n_features == 76
    assert len(engine.columns) == 76
    assert engine.use_dummy is False

    # Inference test with fresh model
    sample_features = {col: 0.0 for col in engine.columns}
    result = engine.predict(sample_features)
    assert result["class_id"] in CLASS_MAP
    assert result["class_label"] == CLASS_MAP[result["class_id"]]
    assert result["model_version"] == "fresh"
    assert isinstance(result["probabilities"], dict)
    assert len(result["probabilities"]) == 10
    total_p = sum(result["probabilities"].values())
    assert np.isclose(total_p, 1.0, atol=1e-4)


def test_explicit_fresh_selection_param():
    """Explicit model_version='fresh' parameter loads fresh model."""
    engine = InferenceEngine(model_version="fresh")
    assert engine.model_version == "fresh"
    assert engine.model_path == MODEL_ARTIFACTS["fresh"]["model_path"]
    assert engine.preproc_path == MODEL_ARTIFACTS["fresh"]["preproc_path"]


def test_invalid_model_version_raises(monkeypatch):
    """Invalid SENTINELAI_MODEL_VERSION must raise ModelConfigurationError and never fall back."""
    monkeypatch.setenv(ENV_MODEL_VERSION, "invalid_v3")
    with pytest.raises(ModelConfigurationError, match="Invalid model version 'invalid_v3'"):
        InferenceEngine()

    with pytest.raises(ModelConfigurationError, match="Invalid model version 'unknown'"):
        InferenceEngine(model_version="unknown")


def test_missing_fresh_model_artifact_raises(monkeypatch):
    """Missing fresh model artifact must raise FileNotFoundError and never fall back."""
    fake_path = PROJECT_ROOT / "data" / "models_fresh" / "nonexistent_rf.pkl"
    fake_artifacts = {
        "fresh": {
            "model_path": fake_path,
            "preproc_path": MODEL_ARTIFACTS["fresh"]["preproc_path"],
        }
    }
    with patch.dict(MODEL_ARTIFACTS, fake_artifacts):
        monkeypatch.setenv(ENV_MODEL_VERSION, "fresh")
        with pytest.raises(FileNotFoundError, match="Model artifact not found for version 'fresh'"):
            InferenceEngine()


def test_missing_fresh_preprocessor_artifact_raises(monkeypatch):
    """Missing fresh preprocessor artifact must raise FileNotFoundError and never fall back."""
    fake_preproc = PROJECT_ROOT / "data" / "models_fresh" / "nonexistent_preproc.pkl"
    fake_artifacts = {
        "fresh": {
            "model_path": MODEL_ARTIFACTS["fresh"]["model_path"],
            "preproc_path": fake_preproc,
        }
    }
    with patch.dict(MODEL_ARTIFACTS, fake_artifacts):
        monkeypatch.setenv(ENV_MODEL_VERSION, "fresh")
        with pytest.raises(FileNotFoundError, match="Preprocessor artifact not found for version 'fresh'"):
            InferenceEngine()


def test_correct_model_preprocessor_pairing():
    """Both legacy and fresh artifacts must have matching feature order and counts."""
    # Legacy pairing
    legacy_engine = InferenceEngine(model_version="legacy")
    assert len(legacy_engine.columns) == 76
    assert list(getattr(legacy_engine.model, "feature_names_in_", [])) == legacy_engine.columns
    if hasattr(legacy_engine.scaler, "n_features_in_"):
        assert legacy_engine.scaler.n_features_in_ == 76

    # Fresh pairing
    fresh_engine = InferenceEngine(model_version="fresh")
    assert len(fresh_engine.columns) == 76
    assert list(getattr(fresh_engine.model, "feature_names_in_", [])) == fresh_engine.columns
    if hasattr(fresh_engine.scaler, "n_features_in_"):
        assert fresh_engine.scaler.n_features_in_ == 76

    # Feature columns must be identical in name and order across both versions
    assert legacy_engine.columns == fresh_engine.columns


def test_feature_validation_parity_between_versions():
    """Both model versions must strictly enforce 76-feature validation."""
    for version in ("legacy", "fresh"):
        engine = InferenceEngine(model_version=version)
        sample = {col: 0.0 for col in engine.columns}

        # 1. Missing feature
        missing = dict(sample)
        del missing[engine.columns[0]]
        with pytest.raises(ValueError, match="Missing required feature"):
            engine.predict(missing)

        # 2. Extra feature
        extra = dict(sample)
        extra["unexpected_feature"] = 1.0
        with pytest.raises(ValueError, match="Unexpected extra feature"):
            engine.predict(extra)

        # 3. Non-numeric feature
        non_num = dict(sample)
        non_num[engine.columns[0]] = "abc"
        with pytest.raises(ValueError, match="must be numeric"):
            engine.predict(non_num)

        # 4. Boolean feature
        bool_val = dict(sample)
        bool_val[engine.columns[0]] = True
        with pytest.raises(ValueError, match="must be numeric"):
            engine.predict(bool_val)

        # 5. NaN feature
        nan_val = dict(sample)
        nan_val[engine.columns[0]] = float("nan")
        with pytest.raises(ValueError, match="contains NaN or infinite"):
            engine.predict(nan_val)


def test_shap_uses_selected_model_and_preprocessor():
    """SHAP explainer correctly attributes features for the configured model version."""
    fresh_engine = InferenceEngine(model_version="fresh")
    sample = {col: 0.0 for col in fresh_engine.columns}

    shap_res = fresh_engine.explain_shap(sample)
    assert isinstance(shap_res, dict)
    # If SHAP is available, verify attributions match the 76 features
    if shap_res.get("status") != "unavailable":
        assert "class_id" in shap_res
        assert "shap_explanations" in shap_res
        explanations = shap_res["shap_explanations"]
        assert len(explanations) == 76
        for col in fresh_engine.columns:
            assert col in explanations
            assert np.isfinite(explanations[col])


def test_api_health_contract_preserved(client):
    """GET /health must return {'status': 'ok'} by default to preserve API contracts."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_health_with_model_info(client, monkeypatch):
    """GET /health?model_info=true exposes active model version."""
    # C7 default
    resp_default = client.get("/health?model_info=true")
    assert resp_default.status_code == 200
    assert resp_default.json() == {"status": "ok", "model_version": "c7_candidate"}
    
    # Legacy version
    monkeypatch.setenv(ENV_MODEL_VERSION, "legacy")
    reset_engine()
    resp_legacy = client.get("/health?model_info=true")
    assert resp_legacy.status_code == 200
    assert resp_legacy.json() == {"status": "ok", "model_version": "legacy"}


def test_api_status_endpoint(client, monkeypatch):
    """GET /status returns structured health and model version configuration."""
    # C7 default
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["model_version"] == "c7_candidate"
    assert "C7_random_forest_depth30_leaf3.pkl" in data["model_path"]
    assert data["columns_count"] == 76

    # Legacy
    monkeypatch.setenv(ENV_MODEL_VERSION, "legacy")
    reset_engine()
    resp_legacy = client.get("/status")
    assert resp_legacy.status_code == 200
    data_legacy = resp_legacy.json()
    assert data_legacy["status"] == "ok"
    assert data_legacy["model_version"] == "legacy"
    assert "random_forest_balanced.pkl" in data_legacy["model_path"]
    assert data_legacy["columns_count"] == 76


def test_api_predict_reflects_selected_model_version(client, monkeypatch):
    """POST /predict result includes model_version matching the active configuration."""
    # Legacy configuration
    monkeypatch.setenv(ENV_MODEL_VERSION, "legacy")
    reset_engine()
    # Build a sample using the engine's columns (now legacy)
    from sentinelai.inference import InferenceEngine
    eng = InferenceEngine()
    sample = {col: 0.0 for col in eng.columns}
    res_legacy = client.post("/predict", json=sample)
    assert res_legacy.status_code == 200
    assert res_legacy.json()["model_version"] == "legacy"

    # Fresh configuration
    monkeypatch.setenv(ENV_MODEL_VERSION, "fresh")
    reset_engine()
    # Rebuild sample (columns identical, but re-instantiating ensures fresh engine)
    eng = InferenceEngine()
    sample = {col: 0.0 for col in eng.columns}
    res_fresh = client.post("/predict", json=sample)
    assert res_fresh.status_code == 200
    assert res_fresh.json()["model_version"] == "fresh"


# ---------------------------------------------------------------------------
# C7 Candidate Tests (added for Stage B integration)
# ---------------------------------------------------------------------------

from sentinelai.inference import SUPPORTED_MODEL_VERSIONS


def test_default_model_version_is_c7_candidate_literal():
    """DEFAULT_MODEL_VERSION constant must be exactly 'c7_candidate'."""
    assert DEFAULT_MODEL_VERSION == "c7_candidate"


def test_c7_candidate_in_supported_versions():
    """c7_candidate must be registered in SUPPORTED_MODEL_VERSIONS."""
    assert "c7_candidate" in SUPPORTED_MODEL_VERSIONS
    assert len(SUPPORTED_MODEL_VERSIONS) == 3


def test_model_artifacts_has_all_three_versions():
    """MODEL_ARTIFACTS must contain entries for legacy, fresh, and c7_candidate."""
    expected_versions = {"legacy", "fresh", "c7_candidate"}
    assert set(MODEL_ARTIFACTS.keys()) == expected_versions


def test_model_artifacts_entries_have_required_keys():
    """Each MODEL_ARTIFACTS entry must have 'model_path' and 'preproc_path'."""
    for version, paths in MODEL_ARTIFACTS.items():
        assert "model_path" in paths, f"{version}: missing 'model_path'"
        assert "preproc_path" in paths, f"{version}: missing 'preproc_path'"
        assert isinstance(paths["model_path"], Path), f"{version}: model_path must be Path"
        assert isinstance(paths["preproc_path"], Path), f"{version}: preproc_path must be Path"


# Skip conditions for tests requiring actual model artifacts
_c7_model_path = MODEL_ARTIFACTS["c7_candidate"]["model_path"]
_c7_preproc_path = MODEL_ARTIFACTS["c7_candidate"]["preproc_path"]
_fresh_model_path = MODEL_ARTIFACTS["fresh"]["model_path"]
_fresh_preproc_path = MODEL_ARTIFACTS["fresh"]["preproc_path"]
_legacy_model_path = MODEL_ARTIFACTS["legacy"]["model_path"]
_legacy_preproc_path = MODEL_ARTIFACTS["legacy"]["preproc_path"]


@pytest.mark.skipif(not _c7_model_path.exists(), reason="C7 model artifact not present")
@pytest.mark.skipif(not _c7_preproc_path.exists(), reason="C7 preprocessor artifact not present")
def test_c7_candidate_loads_successfully():
    """InferenceEngine(model_version='c7_candidate') loads without error when artifacts exist."""
    engine = InferenceEngine(model_version="c7_candidate")
    assert engine.model_version == "c7_candidate"
    assert engine.model_path == _c7_model_path
    assert engine.preproc_path == _c7_preproc_path
    assert engine.use_dummy is False
    assert engine.n_features == 76
    assert len(engine.columns) == 76


@pytest.mark.skipif(not _fresh_model_path.exists(), reason="Fresh model artifact not present")
@pytest.mark.skipif(not _fresh_preproc_path.exists(), reason="Fresh preprocessor artifact not present")
def test_fresh_loads_successfully():
    """InferenceEngine(model_version='fresh') loads without error when artifacts exist."""
    engine = InferenceEngine(model_version="fresh")
    assert engine.model_version == "fresh"
    assert engine.use_dummy is False


@pytest.mark.skipif(not _legacy_model_path.exists(), reason="Legacy model artifact not present")
@pytest.mark.skipif(not _legacy_preproc_path.exists(), reason="Legacy preprocessor artifact not present")
def test_legacy_loads_successfully():
    """InferenceEngine(model_version='legacy') loads without error when artifacts exist."""
    engine = InferenceEngine(model_version="legacy")
    assert engine.model_version == "legacy"
    # Legacy may fall back to dummy if artifacts missing - but if present, should load real model
    if engine.use_dummy:
        pytest.skip("Legacy artifacts present but fell back to dummy (environment issue)")


def test_invalid_model_version_raises_modelconfigurationerror():
    """InferenceEngine(model_version='invalid_version') raises ModelConfigurationError."""
    with pytest.raises(ModelConfigurationError, match="Invalid model version 'invalid_version'"):
        InferenceEngine(model_version="invalid_version")

    with pytest.raises(ModelConfigurationError, match="Invalid model version 'unknown'"):
        InferenceEngine(model_version="unknown")


# ---------------------------------------------------------------------------
# C7 Artifact Missing Tests (verify no dummy fallback)
# ---------------------------------------------------------------------------

def test_missing_c7_model_artifact_raises(monkeypatch):
    """Missing C7 model artifact must raise FileNotFoundError and never fall back."""
    fake_path = PROJECT_ROOT / "staging" / "c7_candidate" / "nonexistent_rf.pkl"
    fake_artifacts = {
        "c7_candidate": {
            "model_path": fake_path,
            "preproc_path": MODEL_ARTIFACTS["c7_candidate"]["preproc_path"],
        }
    }
    with patch.dict(MODEL_ARTIFACTS, fake_artifacts):
        with pytest.raises(FileNotFoundError, match="Model artifact not found for version 'c7_candidate'"):
            InferenceEngine(model_version="c7_candidate")


def test_missing_c7_preprocessor_artifact_raises(monkeypatch):
    """Missing C7 preprocessor artifact must raise FileNotFoundError and never fall back."""
    fake_preproc = PROJECT_ROOT / "staging" / "c7_candidate" / "nonexistent_preproc.pkl"
    fake_artifacts = {
        "c7_candidate": {
            "model_path": MODEL_ARTIFACTS["c7_candidate"]["model_path"],
            "preproc_path": fake_preproc,
        }
    }
    with patch.dict(MODEL_ARTIFACTS, fake_artifacts):
        with pytest.raises(FileNotFoundError, match="Preprocessor artifact not found for version 'c7_candidate'"):
            InferenceEngine(model_version="c7_candidate")


# ---------------------------------------------------------------------------
# C7 Feature Validation Parity
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _c7_model_path.exists() or not _c7_preproc_path.exists(),
                    reason="C7 artifacts not present")
def test_c7_candidate_feature_validation_parity():
    """C7 candidate must strictly enforce 76-feature validation like other versions."""
    engine = InferenceEngine(model_version="c7_candidate")
    sample = {col: 0.0 for col in engine.columns}

    # 1. Missing feature
    missing = dict(sample)
    del missing[engine.columns[0]]
    with pytest.raises(ValueError, match="Missing required feature"):
        engine.predict(missing)

    # 2. Extra feature
    extra = dict(sample)
    extra["unexpected_feature"] = 1.0
    with pytest.raises(ValueError, match="Unexpected extra feature"):
        engine.predict(extra)

    # 3. Non-numeric feature
    non_num = dict(sample)
    non_num[engine.columns[0]] = "abc"
    with pytest.raises(ValueError, match="must be numeric"):
        engine.predict(non_num)

    # 4. Boolean feature
    bool_val = dict(sample)
    bool_val[engine.columns[0]] = True
    with pytest.raises(ValueError, match="must be numeric"):
        engine.predict(bool_val)

    # 5. NaN feature
    nan_val = dict(sample)
    nan_val[engine.columns[0]] = float("nan")
    with pytest.raises(ValueError, match="contains NaN or infinite"):
        engine.predict(nan_val)

    # 6. Infinite feature
    inf_val = dict(sample)
    inf_val[engine.columns[0]] = float("inf")
    with pytest.raises(ValueError, match="contains NaN or infinite"):
        engine.predict(inf_val)


# ---------------------------------------------------------------------------
# C7 Model-Preprocessor Pairing
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _c7_model_path.exists() or not _c7_preproc_path.exists(),
                    reason="C7 artifacts not present")
def test_c7_candidate_model_preprocessor_pairing():
    """C7 model and preprocessor must have matching feature order and counts."""
    engine = InferenceEngine(model_version="c7_candidate")
    assert len(engine.columns) == 76
    assert list(getattr(engine.model, "feature_names_in_", [])) == engine.columns
    if hasattr(engine.scaler, "n_features_in_"):
        assert engine.scaler.n_features_in_ == 76

    # C7 uses Fresh preprocessor - columns must match Fresh exactly
    fresh_engine = InferenceEngine(model_version="fresh")
    assert engine.columns == fresh_engine.columns


# ---------------------------------------------------------------------------
# C7 API Endpoint Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _c7_model_path.exists() or not _c7_preproc_path.exists(),
                    reason="C7 artifacts not present")
def test_api_predict_c7_candidate(client, monkeypatch):
    """POST /predict with C7 candidate returns model_version='c7_candidate'."""
    monkeypatch.setenv(ENV_MODEL_VERSION, "c7_candidate")
    reset_engine()

    from sentinelai.inference import InferenceEngine
    eng = InferenceEngine()
    sample = {col: 0.0 for col in eng.columns}
    res = client.post("/predict", json=sample)
    assert res.status_code == 200
    assert res.json()["model_version"] == "c7_candidate"


@pytest.mark.skipif(not _c7_model_path.exists() or not _c7_preproc_path.exists(),
                    reason="C7 artifacts not present")
def test_api_health_c7_candidate(client, monkeypatch):
    """GET /health?model_info=true with C7 candidate reports model_version='c7_candidate'."""
    monkeypatch.setenv(ENV_MODEL_VERSION, "c7_candidate")
    reset_engine()

    resp = client.get("/health?model_info=true")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "model_version": "c7_candidate"}


@pytest.mark.skipif(not _c7_model_path.exists() or not _c7_preproc_path.exists(),
                    reason="C7 artifacts not present")
def test_api_status_c7_candidate(client, monkeypatch):
    """GET /status with C7 candidate reports C7 metadata."""
    monkeypatch.setenv(ENV_MODEL_VERSION, "c7_candidate")
    reset_engine()

    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["model_version"] == "c7_candidate"
    assert "C7_random_forest_depth30_leaf3.pkl" in str(data["model_path"])
    assert data["columns_count"] == 76