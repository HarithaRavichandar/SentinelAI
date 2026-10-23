import pytest
import numpy as np
from sentinelai.inference import InferenceEngine, CLASS_MAP

@pytest.fixture(scope="module")
def engine():
    return InferenceEngine()

def test_valid_prediction(engine):
    # Construct a valid feature dict with zeros for all required columns
    valid_features = {col: 0.0 for col in engine.columns}
    result = engine.predict(valid_features)
    # Basic structure checks
    assert "class_id" in result
    assert "class_label" in result
    assert "probabilities" in result
    # Class ID should be valid and map to a known label
    assert isinstance(result["class_id"], int)
    assert result["class_id"] in CLASS_MAP
    assert result["class_label"] == CLASS_MAP[result["class_id"]]
    # Probabilities (if present) should be finite, within [0,1] and sum approx 1
    probs = result["probabilities"]
    if probs:
        total = sum(probs.values())
        assert np.isclose(total, 1.0, atol=1e-5)
        for p in probs.values():
            assert 0.0 <= p <= 1.0
        # Keys must correspond to model's class IDs
        assert set(probs.keys()) == set(engine.model.classes_)

def test_missing_feature_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    # Remove one required feature
    missing_key = engine.columns[0]
    del features[missing_key]
    with pytest.raises(ValueError, match="Missing required feature"):
        engine.predict(features)

def test_extra_feature_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    features["extra_feature"] = 1.0
    with pytest.raises(ValueError, match="Unexpected extra feature"):
        engine.predict(features)

def test_non_numeric_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    features[engine.columns[1]] = "non-numeric"
    with pytest.raises(ValueError, match="must be numeric"):
        engine.predict(features)

def test_boolean_input_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    features[engine.columns[2]] = True
    with pytest.raises(ValueError, match="must be numeric"):
        engine.predict(features)

def test_nan_input_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    features[engine.columns[3]] = np.nan
    with pytest.raises(ValueError, match="contains NaN or infinite"):
        engine.predict(features)

def test_pos_inf_input_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    features[engine.columns[4]] = np.inf
    with pytest.raises(ValueError, match="contains NaN or infinite"):
        engine.predict(features)

def test_neg_inf_input_raises(engine):
    features = {col: 0.0 for col in engine.columns}
    features[engine.columns[5]] = -np.inf
    with pytest.raises(ValueError, match="contains NaN or infinite"):
        engine.predict(features)

def test_invalid_input_type_raises(engine):
    with pytest.raises(ValueError, match="Input must be a dict"):
        engine.predict([1, 2, 3])

# Ensure that model and scaler are loaded without fitting
def test_model_and_scaler_loaded(engine):
    assert hasattr(engine, "model")
    assert hasattr(engine, "scaler")
    # Verify the scaler is already fitted using sklearn's utility
    from sklearn.utils.validation import check_is_fitted
    try:
        check_is_fitted(engine.scaler)
    except Exception as e:
        pytest.fail(f"Scaler is not fitted: {e}")
    # Verify the scaler's expected feature count matches the engine's n_features
    if hasattr(engine.scaler, "n_features_in_"):
        assert engine.scaler.n_features_in_ == engine.n_features
    else:
        # Fallback: some scalers expose "n_features_"
        assert getattr(engine.scaler, "n_features_", None) == engine.n_features
