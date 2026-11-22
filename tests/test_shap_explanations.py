import builtins
import importlib
import json
import pathlib
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sentinelai.api import app
from sentinelai.inference import InferenceEngine

client = TestClient(app)

# Helper to create a dummy feature set matching the engine's columns
def dummy_features(columns):
    return {col: 1.0 for col in columns}

# Fixture to get a fresh engine and monkeypatch its heavy components
@pytest.fixture
def engine(monkeypatch):
    eng = InferenceEngine()
    # Ensure dummy mode is off
    eng.use_dummy = False
    # Replace scaler with identity
    class IdentityScaler:
        def transform(self, X):
            return X.values
    eng.scaler = IdentityScaler()
    # Set columns to a small set for testing
    eng.columns = ["f1", "f2", "f3"]
    eng.n_features = len(eng.columns)
    # Dummy model with two classes
    class DummyModel:
        classes_ = [0, 1]
        def predict(self, X):
            return [1]
        def predict_proba(self, X):
            return [[0.3, 0.7]]
    eng.model = DummyModel()
    return eng

def test_shap_success_list(engine, monkeypatch):
    # Mock shap module with TreeExplainer returning list of arrays
    class DummyExplainer:
        def __init__(self, model, **kwargs):
            pass
        def shap_values(self, X):
            # Return list: one array per class, each shape (1, n_features)
            arr0 = np.array([[0.1, 0.2, 0.3]])
            arr1 = np.array([[0.4, 0.5, 0.6]])
            return [arr0, arr1]
    shap_mod = MagicMock()
    shap_mod.TreeExplainer = DummyExplainer
    monkeypatch.setitem(sys.modules, "shap", shap_mod)
    result = engine.explain_shap(dummy_features(engine.columns))
    assert result.get("status") != "unavailable"
    assert result["class_id"] == 1
    expected = {"f1": 0.4, "f2": 0.5, "f3": 0.6}
    assert result["shap_explanations"] == expected

def test_shap_success_numpy(engine, monkeypatch):
    class DummyExplainer:
        def __init__(self, model, **kwargs):
            pass
        def shap_values(self, X):
            # Shape (1, n_features, n_classes)
            arr = np.array([[[0.1, 0.4],
                             [0.2, 0.5],
                             [0.3, 0.6]]])  # (1,3,2)
            return arr
    shap_mod = MagicMock()
    shap_mod.TreeExplainer = DummyExplainer
    monkeypatch.setitem(sys.modules, "shap", shap_mod)
    result = engine.explain_shap(dummy_features(engine.columns))
    assert result.get("status") != "unavailable"
    assert result["class_id"] == 1
    expected = {"f1": 0.4, "f2": 0.5, "f3": 0.6}
    assert result["shap_explanations"] == expected

def test_shap_unavailable_no_shap(engine, monkeypatch):
    # Ensure importing shap raises ImportError by mocking builtins.__import__
    import builtins
    original_import = builtins.__import__

    def import_mock(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "shap":
            raise ImportError("No module named shap")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_mock)
    result = engine.explain_shap(dummy_features(engine.columns))
    assert result["status"] == "unavailable"
    assert "SHAP library not installed" in result["reason"]

def test_shap_unavailable_dummy_mode(engine):
    engine.use_dummy = True
    result = engine.explain_shap(dummy_features(engine.columns))
    assert result["status"] == "unavailable"
    assert "engine in dummy mode" in result["reason"]

def test_shap_invalid_shape_list_length(engine, monkeypatch):
    class DummyExplainer:
        def __init__(self, model, **kwargs):
            pass
        def shap_values(self, X):
            # Return list with wrong length
            return [np.array([[0.1, 0.2, 0.3]])]
    shap_mod = MagicMock()
    shap_mod.TreeExplainer = DummyExplainer
    monkeypatch.setitem(sys.modules, "shap", shap_mod)
    result = engine.explain_shap(dummy_features(engine.columns))
    assert result["status"] == "unavailable"
    assert "SHAP list length does not match" in result["reason"]

def test_shap_non_finite_value(engine, monkeypatch):
    class DummyExplainer:
        def __init__(self, model, **kwargs):
            pass
        def shap_values(self, X):
            arr0 = np.array([[0.1, 0.2, 0.3]])
            arr1 = np.array([[np.nan, 0.5, 0.6]])
            return [arr0, arr1]
    shap_mod = MagicMock()
    shap_mod.TreeExplainer = DummyExplainer
    monkeypatch.setitem(sys.modules, "shap", shap_mod)
    result = engine.explain_shap(dummy_features(engine.columns))
    assert result["status"] == "unavailable"
    assert "non‑finite SHAP" in result["reason"]

def test_triage_shap_integration(monkeypatch):
    dummy_res = {"class_id": 1, "shap_explanations": {"f1": 0.1, "f2": 0.2, "f3": 0.3}}
    with patch.object(InferenceEngine, "explain_shap", return_value=dummy_res):
        fixture_path = pathlib.Path(__file__).parent / "fixtures" / "sample_features.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        response = client.post("/triage?explain_shap=true", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["shap_explanations"] == dummy_res["shap_explanations"]
        # shap_status should be absent when successful
        assert "shap_status" not in data or data["shap_status"] is None
