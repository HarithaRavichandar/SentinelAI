# tests/test_data_split.py
"""Unit tests for the leak‑resistant data splitting pipeline.

The tests focus on:
1. Correct shapes and boolean dtype of the returned masks.
2. Disjointness of the train/val/test partitions.
3. Group integrity – rows that belong to the same duplicate‑feature group are not
   split across different partitions.
4. Reproducibility – running the split twice with the same seed yields identical
   masks.

The tests use the actual dataset files under ``data/raw`` but write the split
outputs to a temporary directory under ``tests/tmp`` to avoid contaminating the
project's ``data/processed`` folder.
"""

from pathlib import Path
import shutil
import tempfile
import numpy as np
import pandas as pd

from sentinelai.data.split import (
    prepare_and_split,
    group_by_exact_features,
)

# Repository root (two levels up from this test file)
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "data" / "raw" / "Data.csv"
LABEL_PATH = REPO_ROOT / "data" / "raw" / "Label.csv"
README_PATH = REPO_ROOT / "data" / "raw" / "Readme.txt"
REPORT_PATH = REPO_ROOT / "reports" / "split_report_test.md"

def _run_split(tmp_dir: Path, seed: int = 42):
    """Helper that runs ``prepare_and_split`` directing outputs to ``tmp_dir``.
    Returns the three boolean masks.
    """
    return prepare_and_split(
        data_path=DATA_PATH,
        label_path=LABEL_PATH,
        readme_path=README_PATH,
        output_dir=tmp_dir,
        report_path=REPORT_PATH,
        seed=seed,
    )

def test_masks_shape_and_dtype():
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        train_mask, val_mask, test_mask = _run_split(tmp_dir)
        # Load the data to know the expected number of rows
        df = pd.read_csv(DATA_PATH, low_memory=False)
        n_rows = df.shape[0]
        assert train_mask.shape == (n_rows,)
        assert val_mask.shape == (n_rows,)
        assert test_mask.shape == (n_rows,)
        assert train_mask.dtype == bool
        assert val_mask.dtype == bool
        assert test_mask.dtype == bool

def test_partitions_disjoint_and_complete():
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        train_mask, val_mask, test_mask = _run_split(tmp_dir)
        # No overlap between partitions
        assert not np.any(np.logical_and(train_mask, val_mask))
        assert not np.any(np.logical_and(train_mask, test_mask))
        assert not np.any(np.logical_and(val_mask, test_mask))
        # All rows belong to exactly one partition
        total_assigned = train_mask.sum() + val_mask.sum() + test_mask.sum()
        df = pd.read_csv(DATA_PATH, low_memory=False)
        assert total_assigned == df.shape[0]

def test_group_integrity():
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        train_mask, val_mask, test_mask = _run_split(tmp_dir)
        df = pd.read_csv(DATA_PATH, low_memory=False)
        group_ids = group_by_exact_features(df)
        # For each group ensure all its rows are in the same partition
        for gid, rows in group_ids.groupby(group_ids):
            in_train = train_mask[rows.index]
            in_val = val_mask[rows.index]
            in_test = test_mask[rows.index]
            # Exactly one of the three should be all True, the others all False
            assert (in_train.all() or in_val.all() or in_test.all()), "Group split across partitions"
            assert not (in_train.any() and in_val.any()), "Group split across train/val"
            assert not (in_train.any() and in_test.any()), "Group split across train/test"
            assert not (in_val.any() and in_test.any()), "Group split across val/test"

def test_reproducibility():
    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        mask1 = _run_split(Path(td1))
        mask2 = _run_split(Path(td2))
        for m1, m2 in zip(mask1, mask2):
            np.testing.assert_array_equal(m1, m2)

# Cleanup the test report if it was created
if REPORT_PATH.exists():
    try:
        REPORT_PATH.unlink()
    except Exception:
        pass
