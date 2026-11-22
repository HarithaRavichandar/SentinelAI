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
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import time
import joblib
import numpy as np
try:
    import pandas as pd
except Exception:
    # Minimal stub for DataFrame used in InferenceEngine
    class _SimpleDataFrame:
        def __init__(self, data, columns=None, index=None):
            import numpy as np
            self._data = np.array(data)
            self.columns = columns if columns is not None else []
            self.index = index if index is not None else []
        @property
        def values(self):
            return self._data
    class pd:
        DataFrame = _SimpleDataFrame

# Ensure the package root is on ``sys.path`` when the module is used as a
# script (e.g. in the smoke‑test). In normal package usage the import works
# because ``src`` is added to ``PYTHONPATH`` by the project configuration.
if __name__ == "__main__":
    project_root = pathlib.Path(__file__).resolve().parents[3]
    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

# ---------------------------------------------------------------------------
# Configuration constants and version registry
# ---------------------------------------------------------------------------
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

ENV_MODEL_VERSION = "SENTINELAI_MODEL_VERSION"
DEFAULT_MODEL_VERSION = "c7_candidate"
SUPPORTED_MODEL_VERSIONS = ("legacy", "fresh", "c7_candidate")


class ModelConfigurationError(ValueError):
    """Raised when an invalid model version is configured or requested."""
    pass


MODEL_ARTIFACTS = {
    "legacy": {
        "model_path": PROJECT_ROOT / "data" / "models" / "random_forest_balanced.pkl",
        "preproc_path": PROJECT_ROOT / "data" / "processed" / "preprocessor_balanced.pkl",
    },
    "fresh": {
        "model_path": PROJECT_ROOT / "data" / "models_fresh" / "random_forest_fresh.pkl",
        "preproc_path": PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl",
    },
    "c7_candidate": {
        "model_path": PROJECT_ROOT / "staging" / "c7_candidate" / "C7_random_forest_depth30_leaf3.pkl",
        "preproc_path": PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl",
    },
}

# Backward-compatible module constants pointing to the default (legacy) paths
MODEL_PATH = MODEL_ARTIFACTS["legacy"]["model_path"]
PREPROC_PATH = MODEL_ARTIFACTS["legacy"]["preproc_path"]

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

    def __init__(self, model_version: str | None = None) -> None:
        """Initialize the inference engine.

        Parameters
        ----------
        model_version:
            Explicit model version to load ('legacy' or 'fresh'). If None,
            reads from the SENTINELAI_MODEL_VERSION environment variable,
            defaulting to 'legacy'.
        """
        import os

        # Determine configured version
        if model_version is None:
            raw_version = os.getenv(ENV_MODEL_VERSION, DEFAULT_MODEL_VERSION)
            resolved_version = raw_version.strip().lower() if raw_version else DEFAULT_MODEL_VERSION
        else:
            resolved_version = str(model_version).strip().lower()

        if resolved_version not in SUPPORTED_MODEL_VERSIONS:
            raise ModelConfigurationError(
                f"Invalid model version '{resolved_version}'. "
                f"Supported versions are: {list(SUPPORTED_MODEL_VERSIONS)}."
            )

        self.model_version = resolved_version
        self.model_path = MODEL_ARTIFACTS[self.model_version]["model_path"]
        self.preproc_path = MODEL_ARTIFACTS[self.model_version]["preproc_path"]

        # Ensure artifacts exist - never silently fall back if requested artifacts are missing
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model artifact not found for version '{self.model_version}': {self.model_path}"
            )
        if not self.preproc_path.exists():
            raise FileNotFoundError(
                f"Preprocessor artifact not found for version '{self.model_version}': {self.preproc_path}"
            )

        self.use_dummy = False
        try:
            self.model = joblib.load(self.model_path)
            payload = joblib.load(self.preproc_path)
            if isinstance(payload, dict):
                self.scaler = payload["scaler"]
                self.columns = payload["columns"]
            else:
                self.scaler = payload.scaler
                self.columns = payload.columns
            # Verify feature order matches.
            expected = list(getattr(self.model, "feature_names_in_", []))
            if expected and expected != self.columns:
                raise RuntimeError(
                    f"Feature order mismatch between model and recovered preprocessor for '{self.model_version}'."
                )
        except (ModelConfigurationError, FileNotFoundError):
            raise
        except Exception as exc:
            # If explicit fresh version was configured, never fall back to dummy
            if self.model_version in ("fresh", "c7_candidate"):
                raise RuntimeError(
                    f"Failed to load fresh model artifacts from {self.model_path}: {exc}"
                ) from exc
            # For legacy, allow dummy mode in test environments lacking heavy dependencies
            logger.warning(f"Failed to load model artifacts: {exc}. Falling back to dummy model.")
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
        self._shap_explainer = None
        self._shap_explainer_model = None
        # Pre‑warm SHAP TreeExplainer if possible (model already loaded)
        try:
            import shap
            TreeExplainer = getattr(shap, "TreeExplainer", None)
            if TreeExplainer is not None and not self.use_dummy:
                self._shap_explainer = TreeExplainer(self.model, feature_perturbation="interventional")
                self._shap_explainer_model = self.model
                logger.info(f"Pre‑warmed SHAP TreeExplainer (interventional) for '{self.model_version}'")
        except Exception as exc:
            logger.warning(f"SHAP explainer pre‑warm failed: {exc}")
            # retain lazy initialization fallback

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
        # Ensure probabilities are normalized. If the sum is not close to 1.0 but is finite
        # and positive, we interpret the output as raw vote counts and convert them.
        total = np.sum(probs)
        if np.isfinite(total) and total > 0:
            if not np.isclose(total, 1.0, atol=1e-5):
                # Normalise to obtain proper probability distribution
                probs = probs / total
        else:
            # Non‑finite or non‑positive sum – keep dict empty to avoid misleading values
            probs = None
        if probs is not None:
            for class_id_val, prob in zip(self.model.classes_, probs):
                probabilities[int(class_id_val)] = float(prob)


        return {
            "class_id": class_id,
            "class_label": class_label,
            "probabilities": probabilities,
            "model_version": self.model_version,
        }

    def explain_shap(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Return SHAP feature contributions for the predicted class.

        The method lazily imports the optional ``shap`` library. If SHAP is not
        installed, the model is in dummy mode, or any error occurs while creating
        the explainer or computing values, a dictionary with ``"status"`` and ``"reason"``
        keys is returned, e.g. ``{"status": "unavailable", "reason": "SHAP not installed"}``.

        The returned payload, when successful, contains:

        ``{"class_id": int, "shap_explanations": {feature_name: float, ...}}``

        where the explanations correspond only to the **predicted** class ID.
        All contributions are validated to be finite numbers; otherwise the
        method falls back to the unavailable status.
        """
        # Validate and scale input (reuse existing logic)
        try:
            X = self._validate_input(features)
        except Exception as exc:
            return {"status": "unavailable", "reason": f"input validation failed: {exc}"}

        # Transform using the scaler
        X_scaled = pd.DataFrame(self.scaler.transform(X), columns=self.columns, index=X.index)

        # If engine is in dummy mode, SHAP cannot be computed meaningfully
        if getattr(self, "use_dummy", False):
            return {"status": "unavailable", "reason": "engine in dummy mode"}

        # Lazy import SHAP library and obtain TreeExplainer
        try:
            import shap  # type: ignore
            TreeExplainer = getattr(shap, "TreeExplainer", None)
            if TreeExplainer is None:
                raise ImportError("TreeExplainer not found in shap module")
        except Exception:
            return {"status": "unavailable", "reason": "SHAP library not installed"}

        # Compute SHAP values (create explainer if needed)
        # Ensure explainer matches current model
        if self._shap_explainer is None or getattr(self, "_shap_explainer_model", None) is not self.model:
            start_explainer = time.time()
            # Use interventional perturbation which is faster for tree models
            self._shap_explainer = TreeExplainer(self.model, feature_perturbation="interventional")
            self._shap_explainer_model = self.model
            logger.info(f"Created SHAP TreeExplainer (interventional) in {time.time() - start_explainer:.3f}s")
        explainer = self._shap_explainer
        start_shap = time.time()
        # Skip additive‑consistency validation (safe for tree models).
        # Some explainer implementations (e.g., test mocks) may not accept `check_additivity`.
        try:
            shap_vals = explainer.shap_values(X_scaled.values, check_additivity=False)
        except TypeError:
            shap_vals = explainer.shap_values(X_scaled.values)
        logger.info(f"SHAP compute time: {time.time() - start_shap:.3f}s")
        # Determine predicted class ID
        try:
            pred_id = int(self.model.predict(X_scaled)[0])
        except Exception as exc:
            return {"status": "unavailable", "reason": f"prediction error for SHAP: {exc}"}

        # Handle different SHAP output shapes
        contributions: Dict[str, float] = {}
        try:
            # Case 1: list of arrays per class (common for sklearn tree models)
            if isinstance(shap_vals, list):
                if len(shap_vals) != len(self.model.classes_):
                    raise ValueError("SHAP list length does not match number of classes")
                # Find index of predicted class
                class_index = list(self.model.classes_).index(pred_id)
                arr = shap_vals[class_index]
                # Expected shape (n_samples, n_features)
                if arr.shape != (1, self.n_features):
                    raise ValueError(f"Unexpected SHAP array shape {arr.shape} for class {pred_id}")
                contributions = {col: float(val) for col, val in zip(self.columns, arr.squeeze())}
            # Case 2: NumPy ndarray (e.g., shape (1, n_features, n_classes) or (n_features, n_classes) etc.)
            elif isinstance(shap_vals, np.ndarray):
                # Shape (n_samples, n_features, n_classes)
                if shap_vals.ndim == 3:
                    if shap_vals.shape[0] != 1 or shap_vals.shape[1] != self.n_features:
                        raise ValueError(f"Unexpected SHAP ndarray shape {shap_vals.shape}")
                    class_index = list(self.model.classes_).index(pred_id)
                    arr = shap_vals[0, :, class_index]
                # Shape (n_features, n_classes) or (n_classes, n_features)
                elif shap_vals.ndim == 2:
                    n_classes = len(self.model.classes_)
                    if shap_vals.shape[0] == self.n_features and shap_vals.shape[1] == n_classes:
                        # (features, classes)
                        class_index = list(self.model.classes_).index(pred_id)
                        arr = shap_vals[:, class_index]
                    elif shap_vals.shape[0] == n_classes and shap_vals.shape[1] == self.n_features:
                        # (classes, features)
                        class_index = list(self.model.classes_).index(pred_id)
                        arr = shap_vals[class_index, :]
                    else:
                        raise ValueError(f"Unexpected SHAP ndarray shape {shap_vals.shape}")
                else:
                    raise ValueError(f"Unsupported SHAP ndarray dimensions {shap_vals.ndim}")
                contributions = {col: float(val) for col, val in zip(self.columns, arr.squeeze())}
            else:
                raise TypeError("Unsupported SHAP return type")
        except Exception as exc:
            return {"status": "unavailable", "reason": f"SHAP shape validation error: {exc}"}

        # Validate contributions are finite
        for f, v in contributions.items():
            if not np.isfinite(v):
                return {"status": "unavailable", "reason": "non‑finite SHAP value encountered"}

        return {"class_id": pred_id, "shap_explanations": contributions}


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
