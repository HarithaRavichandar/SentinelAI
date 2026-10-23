import pathlib
import sys
from typing import Dict, Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

# Ensure src is on the path when this module is imported directly
if str(pathlib.Path(__file__).parents[2]) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from sentinelai.features.preprocessing import (
    load_data,
    load_masks,
    run_preprocessing,
    detect_conflicting_groups,
)

def _resolve_conflict_mask(df: pd.DataFrame, labels: pd.Series) -> np.ndarray:
    """Return a boolean mask indicating rows that belong to a conflicting label group.

    Mirrors ``detect_conflicting_groups`` but produces a mask for the whole dataset.
    """
    group_ids = df.apply(lambda row: tuple(row.values), axis=1).factorize(sort=True)[0]
    conflict_df = detect_conflicting_groups(df, labels)
    conflict_ids = set(conflict_df.index)
    return np.isin(group_ids, list(conflict_ids))


def build_random_forest(
    project_root: pathlib.Path,
    n_estimators: int = 200,
    max_depth: int | None = None,
    class_weight: str = "balanced",
    random_state: int = 42,
    exclude_conflicts_in: str = "train",
) -> Dict[str, Any]:
    """Prepare and train a RandomForest classifier.

    Parameters
    ----------
    project_root: pathlib.Path
        Root of the SentinelAI repository.
    n_estimators: int
        Number of trees in the forest.
    max_depth: int | None
        Maximum depth of each tree (None = unlimited).
    class_weight: str
        Weighting strategy for imbalanced classes.
    random_state: int
        Seed for reproducibility.
    exclude_conflicts_in: str
        "train" – drop rows that belong to conflicting‑label groups from the
        training partition only (recommended). "none" – keep them.
    """
    # Load raw data and split masks
    data_path = project_root / "data" / "raw" / "Data.csv"
    label_path = project_root / "data" / "raw" / "Label.csv"
    df, labels = load_data(data_path, label_path)
    train_mask, val_mask, test_mask = load_masks(
        project_root / "data" / "processed", len(df)
    )

    # Identify conflicting rows
    conflict_mask = _resolve_conflict_mask(df, labels)
    if exclude_conflicts_in == "train":
        train_mask = train_mask & ~conflict_mask

    # Run the standard preprocessing pipeline (drops constant features, fits scaler on training)
    preproc = run_preprocessing(project_root)
    X_train = preproc["train"]
    X_val = preproc["val"]
    X_test = preproc["test"]
    # Align with possibly cleaned training rows if conflicts were removed
    if exclude_conflicts_in == "train":
        y_train = labels[train_mask]
        X_train = X_train.loc[y_train.index]
    else:
        y_train = labels[train_mask]

    y_val = labels[val_mask]
    y_test = labels[test_mask]

    # Random Forest does not require feature scaling, but we keep the same column order
    rf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        class_weight=class_weight,
        random_state=random_state,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)

    return {
        "model": rf,
        "train_mask": train_mask,
        "val_mask": val_mask,
        "test_mask": test_mask,
        "X_train": X_train,
        "X_val": X_val,
        "X_test": X_test,
        "y_train": y_train,
        "y_val": y_val,
        "y_test": y_test,
        "feature_columns": X_train.columns.tolist(),
    }


def evaluate(
    model: RandomForestClassifier,
    X: pd.DataFrame,
    y: pd.Series,
    name: str = "Validation",
) -> Dict[str, Any]:
    """Compute classification metrics and confusion matrix for a fitted model."""
    preds = model.predict(X)
    report = classification_report(
        y, preds, output_dict=True, zero_division=0, labels=sorted(y.unique())
    )
    cm = confusion_matrix(y, preds, labels=sorted(y.unique()))
    print(f"\n=== {name} Metrics ===")
    for metric in ["precision", "recall", "f1-score"]:
        macro = report["macro avg"][metric]
        weighted = report["weighted avg"][metric]
        print(f"{metric.title():<10} macro={macro:.4f} weighted={weighted:.4f}")
    print(f"Overall accuracy: {report['accuracy']:.4f}")
    print("\nConfusion matrix:")
    print(cm)
    return {"report": report, "confusion": cm}
