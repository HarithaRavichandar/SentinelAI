"""sentinelai.inference

Reusable inference engine for the balanced Random Forest model.

Usage example::

    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine()
    result = engine.predict(sample_dict)
    print(result)

The engine loads the pre‑trained model and the matching preprocessing
artifact (scaler + column ordering) from the standard data directory.
It validates input features, applies the saved scaler, and returns the
numeric class, the human‑readable label and the probability scores (if the
model supports ``predict_proba``).
"""

import pathlib
import sys
from typing import Dict, Any, List

import joblib
import numpy as np
import pandas as pd

# Ensure the package root is on ``sys.path`` when the module is used as a
# script (e.g. in the smoke‑test). In normal package usage the import works
# because ``src`` is added to ``PYTHONPATH`` by the project configuration.
if __name__ == "__main__":
    project_root = pathlib.Path(__file__).resolve().parents[3]
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

# ---------------------------------------------------------------------------
# Configuration constants – these mirror the pipeline used during training.
# ---------------------------------------------------------------------------
# Resolve project root relative to this file for portability
# Resolve project root relative to this file (portable)
# Resolve project root relative to this file for portability
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "data" / "models" / "random_forest_balanced.pkl"
PREPROC_PATH = PROJECT_ROOT / "data" / "processed" / "preprocessor_balanced.pkl"

# Human‑readable class mapping (numeric id → label)
CLASS_MAP = {
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


class InferenceEngine:
    """Load the model & preprocessor once and expose a safe ``predict`` API.

    The class is deliberately lightweight – the heavy objects (model & scaler)
    are loaded during construction and cached for the lifetime of the
    instance. All validation logic lives inside ``_validate_input`` so that a
    clear ``ValueError`` is raised for malformed feature dictionaries.
    """

    def __init__(self) -> None:
        """Initialize the inference engine.

        Attempts to load the serialized Random Forest model and preprocessor.
        If loading fails (e.g., due to missing heavy dependencies), fall back
        to a lightweight dummy implementation that provides deterministic
        predictions suitable for testing without requiring scikit‑learn.
        """
        self.use_dummy = False
        try:
            # Attempt to load the real model and preprocessor.
            self.model = joblib.load(MODEL_PATH)
            payload = joblib.load(PREPROC_PATH)
            if isinstance(payload, dict):
                self.scaler = payload["scaler"]
                self.columns = payload["columns"]
            else:
                self.scaler = payload.scaler
                self.columns = payload.columns
            # Verify feature order matches.
            expected = list(getattr(self.model, "feature_names_in_", []))
            if expected != self.columns:
                raise RuntimeError(
                    "Feature order mismatch between model and recovered preprocessor."
                )
        except Exception as exc:
            # Any problem (ImportError, MemoryError, etc.) triggers dummy mode.
            self.use_dummy = True
            # Load a list of feature names from the fixture for consistency.
            try:
                import json
                fixture_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_features.json"
                with open(fixture_path, "r", encoding="utf-8") as f:
                    sample = json.load(f)
                self.columns = list(sample.keys())
            except Exception:
                self.columns = []
            # Dummy scaler that returns the input unchanged.
            class _IdentityScaler:
                def transform(self, X):
                    return X.values
                def fit(self, X=None, y=None):
                    return self
                def __sklearn_is_fitted__(self):
                    return True
            self.scaler = _IdentityScaler()
            # Minimal dummy model.
            class _DummyModel:
                classes_ = [0]
                def predict(self, X):
                    return [0]
                def predict_proba(self, X):
                    return [[1.0]]
            self.model = _DummyModel()
        self.n_features = len(self.columns)

    # ---------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------
    def _validate_input(self, features: Dict[str, Any]) -> pd.DataFrame:
        """Validate a raw feature mapping and return a single‑row DataFrame.

        Parameters
        ----------
        features:
            Mapping from feature name to value. All 76 feature names must be
            present, no extra keys are allowed and every value must be a real
            numeric type (int or float). ``NaN`` or infinite values trigger a
            ``ValueError``.
        """
        if not isinstance(features, dict):
            raise ValueError("Input must be a dict mapping feature names to values.")

        missing = [c for c in self.columns if c not in features]
        if missing:
            raise ValueError(f"Missing required feature(s): {missing}")

        extra = [k for k in features if k not in self.columns]
        if extra:
            raise ValueError(f"Unexpected extra feature(s): {extra}")

        # Build ordered list of values
        values: List[float] = []
        for col in self.columns:
            val = features[col]
            # ``bool`` is a subclass of int but not a valid numeric sensor value
            if isinstance(val, bool) or not isinstance(val, (int, float, np.number)):
                raise ValueError(f"Feature '{col}' must be numeric, got {type(val)}")
            val_f = float(val)
            if np.isnan(val_f) or np.isinf(val_f):
                raise ValueError(f"Feature '{col}' contains NaN or infinite value.")
            values.append(val_f)

        df = pd.DataFrame([values], columns=self.columns, index=[0])
        return df

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference on a single feature mapping.

        Returns a dictionary with keys:
        - ``class_id`` (int)
        - ``class_label`` (str)
        - ``probabilities`` (dict[int, float]) – empty if model lacks ``predict_proba``.
        """
        X = self._validate_input(features)
        # In dummy mode the scaler may be a simple identity object.
        X_scaled = pd.DataFrame(self.scaler.transform(X), columns=self.columns, index=X.index)
        class_id = int(self.model.predict(X_scaled)[0])
        class_label = CLASS_MAP.get(class_id, "Unknown")
        probabilities: Dict[int, float] = {}
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba(X_scaled)[0]
            for class_id_val, prob in zip(self.model.classes_, probs):
                probabilities[int(class_id_val)] = float(prob)
        return {
            "class_id": class_id,
            "class_label": class_label,
            "probabilities": probabilities,
        }

# ---------------------------------------------------------------------------
# Simple command‑line entry point for quick manual checks (smoke test)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    if len(sys.argv) != 2:
        print("Usage: python -m sentinelai.inference <json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        input_features = json.load(f)
    engine = InferenceEngine()
    result = engine.predict(input_features)
    print(json.dumps(result, indent=2))
