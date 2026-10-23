# src/sentinelai/features/preprocessing.py
"""Preprocessing utilities for SentinelAI Phase 2.

This module provides:

* Loading of raw features, labels and split masks (with integrity checks).
* Detection of constant and near‑constant features.
* Detection of conflicting‑label duplicate groups (re‑using logic from `split.py`).
* A reproducible preprocessing pipeline that drops *truly* constant features **only** after
  confirming that they are constant in the **training** partition, fits a `StandardScaler`
  on the training data, and transforms validation and test sets using the same scaler.
* The fitted scaler and the final column ordering are saved to ``data/processed/preprocessor.pkl``.

The pipeline never modifies the raw CSV files or the split masks and never silently deletes
or relabels the 8,909 records belonging to conflicting‑label groups – those groups are merely
reported for the user to decide on a policy.
"""

from __future__ import annotations

import pathlib
import warnings
from typing import List, Tuple, Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Helper utilities (mostly reused from ``scripts/inspect_features.py``)
# ---------------------------------------------------------------------------

def load_data(data_path: pathlib.Path, label_path: pathlib.Path) -> Tuple[pd.DataFrame, pd.Series]:
    """Load the feature matrix and label vector.

    Returns
    -------
    df_data : pd.DataFrame (float32)
    s_label : pd.Series (int32)
    """
    df = pd.read_csv(data_path, dtype=np.float32)
    s = pd.read_csv(label_path, header=0).squeeze("columns").astype(np.int32)
    if len(df) != len(s):
        raise ValueError(f"Row count mismatch: {len(df)} vs {len(s)}")
    return df, s


def load_masks(mask_dir: pathlib.Path, n_rows: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load train/val/test boolean masks and verify integrity.

    The function checks that each mask has shape ``(n_rows,)``, dtype ``bool``,
    that the three masks are pairwise disjoint and together cover all rows.
    """
    train = np.load(mask_dir / "train_mask.npy")
    val = np.load(mask_dir / "val_mask.npy")
    test = np.load(mask_dir / "test_mask.npy")
    for name, arr in zip(["train", "val", "test"], [train, val, test]):
        if arr.shape != (n_rows,):
            raise ValueError(f"{name}_mask shape {arr.shape} does not match expected {n_rows}")
        if arr.dtype != bool:
            raise ValueError(f"{name}_mask dtype {arr.dtype} is not bool")
    # disjointness
    if not (np.all(np.logical_not(np.logical_and(train, val))) and
            np.all(np.logical_not(np.logical_and(train, test))) and
            np.all(np.logical_not(np.logical_and(val, test)))):
        raise ValueError("Masks overlap – they must be disjoint")
    # coverage
    if not np.all(train | val | test):
        raise ValueError("Masks do not cover all rows")
    return train, val, test


def constant_features(df: pd.DataFrame) -> List[str]:
    """Return a list of column names that are constant (single unique value)."""
    return [col for col in df.columns if df[col].nunique() == 1]


def near_constant_features(df: pd.DataFrame, threshold: float = 0.99) -> List[Tuple[str, float]]:
    """Return columns where a single value accounts for *threshold* (default 99 %) of rows.
    The returned list contains ``(column_name, proportion)`` tuples.
    """
    near = []
    n = len(df)
    for col in df.columns:
        top_freq = df[col].value_counts().iloc[0]
        prop = top_freq / n
        if prop >= threshold:
            near.append((col, prop))
    return near


def detect_conflicting_groups(df: pd.DataFrame, labels: pd.Series) -> pd.DataFrame:
    """Identify duplicate‑feature groups that contain more than one distinct label.
    Returns a DataFrame indexed by ``group_id`` with columns ``size`` and ``label_set``.
    """
    group_ids = df.apply(lambda row: tuple(row.values), axis=1).factorize(sort=True)[0]
    temp = pd.DataFrame({"group_id": group_ids, "label": labels})
    agg = (
        temp.groupby("group_id")
        .agg({"label": lambda x: tuple(sorted(set(x))), "group_id": "size"})
        .rename(columns={"group_id": "size", "label": "label_set"})
    )
    agg["conflict"] = agg["label_set"].apply(lambda s: len(s) > 1)
    return agg[agg["conflict"]]

# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------

def fit_and_transform(
    df: pd.DataFrame,
    train_idx: np.ndarray,
    val_idx: np.ndarray,
    test_idx: np.ndarray,
    constant_drop_threshold: float = 0.0,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, StandardScaler, List[str]]:
    """Fit a ``StandardScaler`` on the training partition and transform all splits.

    Parameters
    ----------
    df : pd.DataFrame
        Full feature matrix (all rows).
    train_idx, val_idx, test_idx : np.ndarray of bool
        Boolean masks indicating the rows belonging to each split.
    constant_drop_threshold : float, optional
        If >0, constant‑feature detection will be performed *only* on the training
        rows and any feature that is constant there will be dropped. The default
        (`0.0`) means *no* constant‑feature dropping (useful for debugging).

    Returns
    -------
    df_train, df_val, df_test : pd.DataFrame
        Transformed dataframes with the same column order (excluding dropped constants).
    scaler : StandardScaler
        The fitted scaler (saved for later reuse).
    dropped_features : list[str]
        Names of constant features that were removed.
    """
    # Identify constant features *in training data* only
    train_df = df[train_idx]
    const_feats = constant_features(train_df) if constant_drop_threshold > 0 else []
    if const_feats:
        warnings.warn(
            f"Dropping {len(const_feats)} truly constant features (training only): {const_feats}",
            UserWarning,
        )
    # Drop them from all splits
    df_reduced = df.drop(columns=const_feats)
    # Preserve column order for reproducibility
    final_columns = list(df_reduced.columns)
    # Fit scaler on training data (after dropping constants)
    scaler = StandardScaler()
    scaler.fit(df_reduced.loc[train_idx])
    # Transform each split
    df_train = pd.DataFrame(scaler.transform(df_reduced.loc[train_idx]), columns=final_columns, index=df_reduced.loc[train_idx].index)
    df_val = pd.DataFrame(scaler.transform(df_reduced.loc[val_idx]), columns=final_columns, index=df_reduced.loc[val_idx].index)
    df_test = pd.DataFrame(scaler.transform(df_reduced.loc[test_idx]), columns=final_columns, index=df_reduced.loc[test_idx].index)
    return df_train, df_val, df_test, scaler, const_feats


def run_preprocessing(project_root: pathlib.Path) -> Dict[str, object]:
    """High‑level entry point used by downstream scripts.

    * Loads raw data and masks.
    * Validates mask integrity.
    * Reports constant / near‑constant features.
    * Fits a ``StandardScaler`` on training data **after** dropping truly constant
      features (as observed in training).
    * Saves the fitted scaler and the final column order to
      ``data/processed/preprocessor.pkl``.
    * Returns a dictionary with the transformed splits and meta‑information.
    """
    data_path = project_root / "data" / "raw" / "Data.csv"
    label_path = project_root / "data" / "raw" / "Label.csv"
    mask_dir = project_root / "data" / "processed"

    df, labels = load_data(data_path, label_path)
    train_mask, val_mask, test_mask = load_masks(mask_dir, len(df))

    # Log constant / near‑constant statistics (using training rows)
    const_feats = constant_features(df[train_mask])
    near_const = near_constant_features(df, threshold=0.99)
    print(f"Constant features in training data ({len(const_feats)}): {const_feats}")
    print(f"Near-constant features (>99% same) across whole set ({len(near_const)}).")

    # Detect conflicting‑label duplicate groups (report only)
    conflict_df = detect_conflicting_groups(df, labels)
    if not conflict_df.empty:
        print(f"Conflicting-label groups: {conflict_df.shape[0]}, rows affected: {conflict_df['size'].sum()}")
        print("These groups are retained; downstream policy must decide whether to filter or keep them.")

    # Fit/transform pipeline (enable dropping constant features)
    df_train, df_val, df_test, scaler, dropped = fit_and_transform(
        df, train_mask, val_mask, test_mask, constant_drop_threshold=1.0
    )

    # Save scaler and column order
    artifact_path = project_root / "data" / "processed" / "preprocessor.pkl"
    payload = {
        "scaler": scaler,
        "columns": df_train.columns.tolist(),
        "dropped_constant_features": dropped,
    }
    joblib.dump(payload, artifact_path)
    print(f"Preprocessor saved to {artifact_path}")

    return {
        "train": df_train,
        "val": df_val,
        "test": df_test,
        "scaler": scaler,
        "dropped_constant_features": dropped,
        "conflict_groups": conflict_df,
    }

# Quick sanity‑check when run as script
if __name__ == "__main__":
    project_root = pathlib.Path(__file__).resolve().parents[2]
    run_preprocessing(project_root)
