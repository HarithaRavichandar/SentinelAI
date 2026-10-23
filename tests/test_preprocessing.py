# tests/test_preprocessing.py
"""Tests for SentinelAI preprocessing utilities.
These tests use synthetic data and do not touch the full dataset.
"""

import pathlib
import numpy as np
import pandas as pd
import pytest

# Ensure src is on path
import sys
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from sentinelai.features.preprocessing import (
    constant_features,
    near_constant_features,
    detect_conflicting_groups,
    load_masks,
)

def test_constant_feature_detection():
    df = pd.DataFrame({
        "constant": [1] * 5,
        "vary": [1, 2, 3, 4, 5],
    })
    const = constant_features(df)
    assert const == ["constant"]

def test_near_constant_detection():
    col = [5] * 8 + [2, 3]
    df = pd.DataFrame({"near": col})
    near = near_constant_features(df, threshold=0.75)
    assert len(near) == 1
    name, prop = near[0]
    assert name == "near"
    assert pytest.approx(prop, 0.01) == 0.8

def test_conflicting_label_detection():
    data = {"f1": [1, 1, 2], "f2": [0, 0, 3]}
    df = pd.DataFrame(data)
    labels = pd.Series([0, 1, 0])
    conflict_df = detect_conflicting_groups(df, labels)
    assert conflict_df.shape[0] == 1
    row = conflict_df.iloc[0]
    assert row["size"] == 2
    assert set(row["label_set"]) == {0, 1}

def test_load_masks_valid(tmp_path):
    n = 10
    train = np.zeros(n, dtype=bool)
    val = np.zeros(n, dtype=bool)
    test = np.zeros(n, dtype=bool)
    train[:5] = True
    val[5:8] = True
    test[8:] = True
    np.save(tmp_path / "train_mask.npy", train)
    np.save(tmp_path / "val_mask.npy", val)
    np.save(tmp_path / "test_mask.npy", test)
    t, v, te = load_masks(tmp_path, n)
    assert np.array_equal(t, train)
    assert np.array_equal(v, val)
    assert np.array_equal(te, test)

def test_load_masks_overlap_error(tmp_path):
    n = 5
    train = np.array([True, True, False, False, False])
    val = np.array([False, True, False, False, False])
    test = np.array([False, False, False, False, True])
    np.save(tmp_path / "train_mask.npy", train)
    np.save(tmp_path / "val_mask.npy", val)
    np.save(tmp_path / "test_mask.npy", test)
    with pytest.raises(ValueError, match="Masks overlap"):
        load_masks(tmp_path, n)
