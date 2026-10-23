import pathlib
import sys
from typing import Dict, Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler

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

def build_classifier(
    project_root: pathlib.Path,
    class_weight: str = "balanced",
    C: float = 1.0,
    max_iter: int = 200,
    exclude_conflicts_in: str = "train",  # "train" or "none"
) -> Dict[str, Any]:
    """Prepare a class‑weighted Logistic Regression baseline.

    This function **does not train** the model. It returns a dictionary containing
    the (un‑fitted) ``LogisticRegression`` instance, the scaler, feature matrices,
    label vectors and the masks used.

    Parameters
    ----------
    project_root: pathlib.Path
        Root of the SentinelAI repository.
    class_weight: str
        ``"balanced"`` to compute inverse‑frequency class weights.
    C, max_iter: float, int
        Regularisation strength and maximum solver iterations.
    exclude_conflicts_in: str
        ``"train"`` – drop rows that belong to conflicting‑label groups from the
        training partition only (recommended). ``"none"`` – keep them.
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
        # Remove conflicting rows from training mask only
        train_mask = train_mask & ~conflict_mask

    # Run the standard preprocessing pipeline (drops constant features, fits scaler on *all* training rows)
    preproc = run_preprocessing(project_root)
    X_train = preproc["train"]
    X_val = preproc["val"]
    X_test = preproc["test"]
    scaler = preproc["scaler"]
    dropped_constants = preproc["dropped_constant_features"]

    # Align labels to the (potentially reduced) training mask
    y_train = labels[train_mask]
    y_val = labels[val_mask]
    y_test = labels[test_mask]

    # If we excluded conflicts from training, refit the scaler on the clean rows
    if exclude_conflicts_in == "train":
        # Align X_train to the cleaned training rows using y_train index
        X_train = X_train.loc[y_train.index]
        # Re‑fit a fresh scaler on the cleaned training data
        scaler = StandardScaler()
        scaler.fit(X_train)
        X_train = pd.DataFrame(scaler.transform(X_train), columns=X_train.columns, index=X_train.index)
        X_val = pd.DataFrame(scaler.transform(X_val), columns=X_val.columns, index=X_val.index)
        X_test = pd.DataFrame(scaler.transform(X_test), columns=X_test.columns, index=X_test.index)

    # Initialise the classifier (still unfitted)
    clf = LogisticRegression(
        penalty="l2",
        C=C,
        max_iter=max_iter,
        solver="lbfgs",
        multi_class="multinomial",
        class_weight=class_weight,
        n_jobs=-1,
    )

    return {
        "model": clf,
        "scaler": scaler,
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
        "dropped_constant_features": dropped_constants,
    }

def evaluate(
    model: LogisticRegression,
    X: pd.DataFrame,
    y: pd.Series,
    name: str = "Validation",
) -> Dict[str, Any]:
    """Compute and print the full suite of classification metrics.
    Returns a dict with ``report`` (classification_report dict) and ``confusion`` matrix.
    """
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
