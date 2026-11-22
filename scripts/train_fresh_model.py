#!/usr/bin/env python3
"""scripts/train_fresh_model.py

Trains the fresh SentinelAI preprocessor and Random Forest model (Step 2).

Key Operations:
1. Loads raw dataset and fresh split masks.
2. Asserts strict mutual exclusivity and zero leakage:
   - Validates that val, test, and conflict rows are strictly excluded.
   - Uses train_mask_fresh.npy (307,304 rows) exclusively.
3. Fits StandardScaler strictly on fresh training rows.
4. Trains RandomForestClassifier with exact configuration:
   - n_estimators = 200
   - class_weight = "balanced"
   - random_state = 101
   - n_jobs = 4 (memory-bounded for Windows environment)
5. Serializes artifacts to data/models_fresh/:
   - preprocessor_fresh.pkl
   - random_forest_fresh.pkl
   - train_fresh_metadata.json
6. Verifies saved artifacts on a small validation sample (smoke inference test).
7. Memory-conscious execution with explicit garbage collection.

Safety Safeguards:
- Does NOT evaluate on test_fresh or calculate test metrics.
- Does NOT modify legacy model artifacts, preprocessors, or masks.
- Does NOT calibrate thresholds or policy weights.
- Feature flag SENTINELAI_TWO_STAGE_TRIAGE remains untouched.
"""

from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Repository root and sys.path setup
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from sentinelai.data.split import _parse_label_mapping, load_features_and_labels


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file efficiently in chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_split_isolation(
    train_mask: np.ndarray,
    val_mask: np.ndarray,
    test_mask: np.ndarray,
    conflict_mask: np.ndarray,
    expected_train_rows: int = 307304,
) -> None:
    """Ensure training rows strictly exclude val, test, and conflict rows."""
    print("Verifying partition isolation and mask integrity...")
    assert train_mask.dtype == bool, "train_mask must be boolean"
    assert val_mask.dtype == bool, "val_mask must be boolean"
    assert test_mask.dtype == bool, "test_mask must be boolean"
    assert conflict_mask.dtype == bool, "conflict_mask must be boolean"

    # Mutual exclusivity assertions
    assert not np.any(train_mask & val_mask), "CRITICAL: train_mask overlaps with val_mask!"
    assert not np.any(train_mask & test_mask), "CRITICAL: train_mask overlaps with test_mask!"
    assert not np.any(train_mask & conflict_mask), "CRITICAL: train_mask overlaps with conflict_mask!"
    assert not np.any(val_mask & test_mask), "CRITICAL: val_mask overlaps with test_mask!"

    train_count = int(train_mask.sum())
    assert train_count == expected_train_rows, (
        f"Expected {expected_train_rows} training rows, got {train_count}"
    )
    print(f"  [PASS] Mask isolation verified. Clean training rows: {train_count:,}")


def smoke_test_artifacts(
    preproc_path: Path,
    model_path: Path,
    data_path: Path,
    val_mask: np.ndarray,
    expected_classes: List[int],
) -> Dict[str, Any]:
    """Verify saved model and preprocessor can be loaded and predict finite scores on validation sample."""
    print("\nRunning smoke test on saved fresh model artifacts...")
    preproc_payload = joblib.load(preproc_path)
    scaler = preproc_payload["scaler"]
    columns = preproc_payload["columns"]
    model: RandomForestClassifier = joblib.load(model_path)

    # Find first 5 validation indices
    val_indices = np.where(val_mask)[0][:5]
    print(f"  Loading 5 validation flows (indices: {list(val_indices)}) for smoke verification...")

    # Read specific rows
    df_sample = pd.read_csv(data_path, skiprows=lambda i: i > 0 and (i - 1) not in val_indices, dtype=np.float32)
    assert len(df_sample) == 5, f"Expected 5 sample rows, got {len(df_sample)}"

    # Transform with recovered scaler
    sample_scaled = pd.DataFrame(scaler.transform(df_sample[columns]), columns=columns)

    # Predict
    preds = model.predict(sample_scaled)
    probs = model.predict_proba(sample_scaled)

    assert len(preds) == 5, "Prediction count mismatch"
    assert probs.shape == (5, len(expected_classes)), f"Probability shape mismatch {probs.shape}"
    assert np.all(np.isfinite(probs)), "Probabilities contain NaN or Inf values!"
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0), "Probabilities out of [0, 1] range!"
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-5), "Probabilities do not sum to 1.0!"

    for i in range(5):
        print(f"    Sample {i+1}: Predicted class {preds[i]} (Top vote: {probs[i].max():.3f})")

    print("  [PASS] Artifact smoke test passed successfully.")
    return {
        "verified": True,
        "sample_predictions": [int(p) for p in preds],
        "sample_top_probs": [float(p.max()) for p in probs],
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    start_time = time.time()
    print("=" * 80)
    print("SentinelAI: Training Fresh Preprocessor and Random Forest Model (Step 2)")
    print("=" * 80)

    # Path setup
    data_path = PROJECT_ROOT / "data" / "raw" / "Data.csv"
    label_path = PROJECT_ROOT / "data" / "raw" / "Label.csv"
    readme_path = PROJECT_ROOT / "data" / "raw" / "Readme.txt"

    mask_dir = PROJECT_ROOT / "data" / "processed_fresh"
    train_mask_path = mask_dir / "train_mask_fresh.npy"
    val_mask_path = mask_dir / "val_mask_fresh.npy"
    test_mask_path = mask_dir / "test_mask_fresh.npy"
    conflict_mask_path = mask_dir / "conflict_mask_fresh.npy"

    models_dir = PROJECT_ROOT / "data" / "models_fresh"
    models_dir.mkdir(parents=True, exist_ok=True)

    preproc_out_path = models_dir / "preprocessor_fresh.pkl"
    model_out_path = models_dir / "random_forest_fresh.pkl"
    metadata_out_path = models_dir / "train_fresh_metadata.json"

    # 1. Dataset Fingerprint
    print("\n[1/7] Computing dataset file hashes...")
    hashes = {
        "Data.csv": compute_file_sha256(data_path),
        "Label.csv": compute_file_sha256(label_path),
        "Readme.txt": compute_file_sha256(readme_path),
    }
    for fname, h in hashes.items():
        print(f"  - {fname}: {h[:16]}...")

    # 2. Load Split Masks and Verify Isolation
    print("\n[2/7] Loading fresh split masks and asserting strict isolation...")
    train_mask = np.load(train_mask_path)
    val_mask = np.load(val_mask_path)
    test_mask = np.load(test_mask_path)
    conflict_mask = np.load(conflict_mask_path)

    verify_split_isolation(
        train_mask=train_mask,
        val_mask=val_mask,
        test_mask=test_mask,
        conflict_mask=conflict_mask,
        expected_train_rows=307304,
    )

    # 3. Load Data & Slice Clean Training Partition
    print("\n[3/7] Loading raw features and slicing clean training partition...")
    df_data, s_label, mapping = load_features_and_labels(data_path, label_path, readme_path)
    feature_columns = list(df_data.columns)

    print(f"  Slicing X_train and y_train ({train_mask.sum():,} rows)...")
    X_train_raw = df_data.loc[train_mask].copy()
    y_train = s_label.loc[train_mask].copy()

    # Free full dataframe from memory immediately
    del df_data
    gc.collect()

    class_counts = y_train.value_counts().to_dict()
    print("  Clean training class distribution:")
    for cid in sorted(mapping.keys()):
        cnt = class_counts.get(cid, 0)
        print(f"    Class {cid} ({mapping[cid]:<15}): {cnt:>7,} flows ({cnt/len(y_train):.2%})")

    # 4. Fit StandardScaler Strictly on Training Rows
    print("\n[4/7] Fitting StandardScaler strictly on fresh training rows...")
    scaler = StandardScaler()
    scaler.fit(X_train_raw)

    assert scaler.n_samples_seen_ == len(y_train), "Scaler sample count mismatch!"
    assert scaler.n_features_in_ == len(feature_columns), "Scaler feature count mismatch!"
    print(f"  StandardScaler fitted on {scaler.n_samples_seen_:,} samples across {scaler.n_features_in_} features.")

    print(f"  Saving preprocessor to {preproc_out_path}...")
    preprocessor_payload = {
        "scaler": scaler,
        "columns": feature_columns,
    }
    joblib.dump(preprocessor_payload, preproc_out_path)
    print("  [PASS] Preprocessor saved.")

    # 5. Transform Training Features
    print("\n[5/7] Transforming training data with fitted scaler...")
    X_train_scaled = pd.DataFrame(
        scaler.transform(X_train_raw),
        columns=feature_columns,
        index=X_train_raw.index,
    )
    # Free raw training dataframe
    del X_train_raw
    gc.collect()

    # 6. Train Random Forest Classifier
    rf_config = {
        "n_estimators": 200,
        "class_weight": "balanced",
        "random_state": 101,
        "n_jobs": 4,
        "verbose": 1,
    }
    print(f"\n[6/7] Training RandomForestClassifier with configuration:")
    print(f"  - n_estimators: {rf_config['n_estimators']}")
    print(f"  - class_weight: {rf_config['class_weight']}")
    print(f"  - random_state: {rf_config['random_state']}")
    print(f"  - n_jobs:       {rf_config['n_jobs']}")

    train_start = time.time()
    rf = RandomForestClassifier(
        n_estimators=rf_config["n_estimators"],
        class_weight=rf_config["class_weight"],
        random_state=rf_config["random_state"],
        n_jobs=rf_config["n_jobs"],
        verbose=rf_config["verbose"],
    )
    rf.fit(X_train_scaled, y_train)
    train_duration = time.time() - train_start
    print(f"  Random Forest training completed in {train_duration:.2f} seconds ({train_duration/60:.2f} minutes).")

    # Free scaled training data
    del X_train_scaled, y_train
    gc.collect()

    print(f"  Saving trained model to {model_out_path}...")
    save_start = time.time()
    joblib.dump(rf, model_out_path)
    save_duration = time.time() - save_start
    print(f"  Model serialized in {save_duration:.2f} seconds.")

    # 7. Smoke Test and Verification
    print("\n[7/7] Verifying saved artifacts and recording training metadata...")
    smoke_res = smoke_test_artifacts(
        preproc_path=preproc_out_path,
        model_path=model_out_path,
        data_path=data_path,
        val_mask=val_mask,
        expected_classes=sorted(mapping.keys()),
    )

    preproc_size_bytes = preproc_out_path.stat().st_size
    model_size_bytes = model_out_path.stat().st_size

    metadata = {
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_type": "RandomForestClassifier",
        "hyperparameters": {
            "n_estimators": rf_config["n_estimators"],
            "class_weight": rf_config["class_weight"],
            "random_state": rf_config["random_state"],
            "n_jobs": rf_config["n_jobs"],
        },
        "training_row_count": int(train_mask.sum()),
        "feature_count": len(feature_columns),
        "feature_order": feature_columns,
        "class_mapping": mapping,
        "training_class_counts": {str(k): int(v) for k, v in class_counts.items()},
        "dataset_hashes": hashes,
        "package_versions": {
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
            "python": platform.python_version(),
        },
        "artifact_sizes": {
            "preprocessor_fresh_pkl_bytes": preproc_size_bytes,
            "preprocessor_fresh_pkl_kb": round(preproc_size_bytes / 1024, 2),
            "random_forest_fresh_pkl_bytes": model_size_bytes,
            "random_forest_fresh_pkl_mb": round(model_size_bytes / (1024 * 1024), 2),
        },
        "timing": {
            "train_duration_seconds": round(train_duration, 2),
            "total_step2_seconds": round(time.time() - start_time, 2),
        },
        "smoke_test": smoke_res,
    }

    with open(metadata_out_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    total_elapsed = time.time() - start_time
    print(f"\nTraining metadata written to {metadata_out_path}")
    print(f"Preprocessor size: {metadata['artifact_sizes']['preprocessor_fresh_pkl_kb']} KB")
    print(f"Model size:        {metadata['artifact_sizes']['random_forest_fresh_pkl_mb']} MB")
    print(f"Step 2 successfully finished in {total_elapsed:.2f} seconds ({total_elapsed/60:.2f} minutes).")
    print("=" * 80)


if __name__ == "__main__":
    main()

