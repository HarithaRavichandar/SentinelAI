# src/sentinelai/data/split.py
"""Leak‑resistant data preparation and train/val/test splitting.

This module implements:
1. Loading of the raw feature matrix (Data.csv) and label vector (Label.csv) with
   strict validation against the class mapping in ``Readme.txt``.
2. Deterministic grouping of *exact* duplicate feature rows using tuple factorisation –
   equality based, therefore collision‑free.
3. Detection of groups that contain conflicting labels and detailed statistics.
4. A group‑aware splitting routine that respects the target 70/15/15 split while
   keeping each duplicate group entirely within a single partition.
5. Generation of a concise but comprehensive split report saved to
   ``reports/split_report.md``.

All operations are memory‑conscious – the whole dataset (~190 MiB) comfortably fits
in RAM, but the implementation can be adapted to a chunked approach if needed.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _parse_label_mapping(readme_path: Path) -> Dict[int, str]:
    """Parse ``Readme.txt`` which contains lines like ``Benign\t\t0``.
    Returns a mapping from numeric ID to class name.
    """
    mapping: Dict[int, str] = {}
    with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    code = int(parts[-1])
                    name = " ".join(parts[:-1])
                    mapping[code] = name
                except ValueError:
                    continue
    return mapping


def load_features_and_labels(
    data_path: Path, label_path: Path, readme_path: Path
) -> Tuple[pd.DataFrame, pd.Series, Dict[int, str]]:
    """Load Data.csv and Label.csv with robust temporary directory handling.

    Pandas may create temporary files during parsing; on Windows the default
    system temp directory can hit resource limits in the CI environment. We
    therefore point ``tempfile.tempdir`` to a lightweight ``tmp`` folder inside
    the repository root (created if missing) before invoking ``pd.read_csv``.
    """
    import tempfile
    from pathlib import Path as _Path
    # Ensure a local temporary directory exists
    local_tmp = _Path(__file__).resolve().parents[2] / "tmp"
    local_tmp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(local_tmp)

    """Load ``Data.csv`` and ``Label.csv`` and validate against the class mapping.

    Returns
    -------
    df_data : pd.DataFrame
        Feature matrix.
    s_label : pd.Series (int dtype)
        Corresponding label vector.
    mapping : dict[int, str]
        Numeric‑to‑class name mapping parsed from ``Readme.txt``.
    """
    mapping = _parse_label_mapping(readme_path)
    if not mapping:
        raise ValueError("Failed to parse any label mapping from Readme.txt")
    df_data = pd.read_csv(data_path, dtype=np.float32, engine='python')
    s_label = pd.read_csv(label_path, header=0).squeeze("columns").astype(np.int32)
    if df_data.shape[0] != s_label.shape[0]:
        raise ValueError(
            f"Row count mismatch: Data.csv ({df_data.shape[0]}) vs Label.csv ({s_label.shape[0]})"
        )
    if df_data.shape[1] == 0:
        raise ValueError("Data.csv appears to have no feature columns")
    unexpected = set(s_label.unique()) - set(mapping.keys())
    if unexpected:
        raise ValueError(
            f"Unexpected label IDs not present in Readme.txt: {sorted(unexpected)}"
        )
    return df_data, s_label, mapping


def group_by_exact_features(df_data: pd.DataFrame) -> pd.Series:
    """Assign a deterministic integer *group_id* to each row based on exact feature values.
    The algorithm converts each row to a ``tuple`` of its values and then ``factorize``
    the series of tuples – this yields a stable integer code for each unique feature
    vector without relying on hashing.
    """
    feature_tuples = df_data.apply(lambda row: tuple(row.values), axis=1)
    group_ids, _ = pd.factorize(feature_tuples, sort=True)
    return pd.Series(group_ids, index=df_data.index, name="group_id")


def detect_conflicting_groups(group_ids: pd.Series, labels: pd.Series) -> pd.DataFrame:
    """Return a DataFrame with groups that have more than one distinct label.
    Columns:
        size – number of rows in the group
        label_set – sorted tuple of distinct labels observed
        conflict – bool flag (True when ``len(label_set) > 1``)
    """
    df = pd.DataFrame({"group_id": group_ids, "label": labels})
    agg = (
        df.groupby("group_id")
        .agg({"label": lambda x: tuple(sorted(set(x))), "group_id": "size"})
        .rename(columns={"group_id": "size", "label": "label_set"})
    )
    agg["conflict"] = agg["label_set"].apply(lambda s: len(s) > 1)
    return agg[agg["conflict"]]


def compute_group_statistics(
    group_ids: pd.Series, labels: pd.Series, conflict_df: pd.DataFrame
) -> Dict[str, int]:
    """Compute a dictionary of useful duplicate‑group statistics.
    Returns keys:
        total_rows, unique_groups, rows_in_duplicate_groups, duplicate_excess_rows,
        conflicting_groups, conflicting_rows.
    """
    total_rows = len(group_ids)
    group_sizes = group_ids.value_counts()
    unique_groups = group_sizes.shape[0]
    rows_in_duplicate_groups = int(group_sizes[group_sizes > 1].sum())
    duplicate_excess_rows = total_rows - unique_groups
    conflicting_groups = conflict_df.shape[0]
    conflicting_rows = int(conflict_df["size"].sum())
    return {
        "total_rows": total_rows,
        "unique_groups": unique_groups,
        "rows_in_duplicate_groups": rows_in_duplicate_groups,
        "duplicate_excess_rows": duplicate_excess_rows,
        "conflicting_groups": conflicting_groups,
        "conflicting_rows": conflicting_rows,
    }


def split_groups_groupaware(
    group_ids: pd.Series,
    labels: pd.Series,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split at *group* level while aiming for the target fractions.
    Returns three boolean masks (train, val, test) aligned with the original rows.
    """
    total = train_frac + val_frac + test_frac
    if not np.isclose(total, 1.0):
        raise ValueError("train_frac + val_frac + test_frac must sum to 1.0")
    rng = random.Random(seed)
    grp_df = pd.DataFrame({"group_id": group_ids, "label": labels})
    summary = (
        grp_df.groupby("group_id")
        .agg({"label": lambda x: x.iloc[0], "group_id": "size"})
        .rename(columns={"group_id": "size", "label": "representative_label"})
    )
    group_list = list(summary.index)
    rng.shuffle(group_list)
    total_rows = len(group_ids)
    target_train = int(total_rows * train_frac)
    target_val = int(total_rows * val_frac)
    target_test = total_rows - target_train - target_val
    train_rows = val_rows = test_rows = 0
    train_mask = np.zeros(total_rows, dtype=bool)
    val_mask = np.zeros(total_rows, dtype=bool)
    test_mask = np.zeros(total_rows, dtype=bool)
    for gid in group_list:
        size = summary.at[gid, "size"]
        deficits = {
            "train": target_train - train_rows,
            "val": target_val - val_rows,
            "test": target_test - test_rows,
        }
        chosen = max(deficits, key=lambda k: deficits[k])
        if chosen == "train":
            train_rows += size
            train_mask[group_ids == gid] = True
        elif chosen == "val":
            val_rows += size
            val_mask[group_ids == gid] = True
        else:
            test_rows += size
            test_mask[group_ids == gid] = True
    return train_mask, val_mask, test_mask


def generate_split_report(
    report_path: Path,
    mapping: Dict[int, str],
    label_counts: Dict[int, int],
    conflict_df: pd.DataFrame,
    group_stats: Dict[str, int],
    split_masks: Tuple[np.ndarray, np.ndarray, np.ndarray],
    train_frac: float,
    val_frac: float,
    test_frac: float,
    seed: int,
    label_series: pd.Series,
) -> None:
    """Write a markdown report summarising the split and duplicate‑group analysis."""
    train_mask, val_mask, test_mask = split_masks
    total = len(train_mask)
    def per_split_counts(mask: np.ndarray) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for cid in sorted(mapping.keys()):
            counts[cid] = int(np.sum(mask & (label_series == cid)))
        return counts
    train_counts = per_split_counts(train_mask)
    val_counts = per_split_counts(val_mask)
    test_counts = per_split_counts(test_mask)
    def fmt_counts(d: Dict[int, int]) -> str:
        return ", ".join([f"{cid}: {cnt}" for cid, cnt in d.items()])
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# SentinelAI – Data Split Report\n\n")
        f.write("> **Purpose** – Produce a leak‑resistant split that keeps duplicate feature groups intact and documents the resulting class balance.\n\n")
        f.write("---\n\n")
        f.write("## 1. Class mapping (from Readme.txt)\n\n")
        f.write("| Numeric ID | Class Name |\n| :---: | :--- |\n")
        for cid, name in sorted(mapping.items()):
            f.write(f"| `{cid}` | {name} |\n")
        f.write("\n---\n\n")
        f.write("## 2. Overall class distribution (before split)\n\n")
        f.write("| Class ID | Count | % of total |\n| :---: | :---: | :---: |\n")
        for cid, cnt in sorted(label_counts.items()):
            pct = round(cnt / total * 100, 3)
            f.write(f"| `{cid}` | {cnt:,} | {pct}% |\n")
        f.write("\n---\n\n")
        f.write("## 3. Duplicate‑group statistics\n\n")
        f.write(f"- Total rows: {group_stats['total_rows']:,}\n")
        f.write(f"- Unique exact feature groups: {group_stats['unique_groups']:,}\n")
        f.write(f"- Rows in groups occurring >1 time: {group_stats['rows_in_duplicate_groups']:,}\n")
        f.write(f"- Duplicate excess rows (total‑unique): {group_stats['duplicate_excess_rows']:,}\n")
        f.write(f"- Groups with conflicting labels: {group_stats['conflicting_groups']:,}\n")
        f.write(f"- Rows affected by label conflicts: {group_stats['conflicting_rows']:,}\n")
        if not conflict_df.empty:
            f.write("  - Example conflicting groups (up to 5):\n")
            for gid, row in conflict_df.head(5).iterrows():
                f.write(f"    - group_id `{gid}` size {row['size']} labels {row['label_set']}\n")
        f.write("\n---\n\n")
        f.write("## 4. Split proportions (row counts)\n\n")
        f.write(f"- Target fractions: train {train_frac:.2%}, val {val_frac:.2%}, test {test_frac:.2%}\n")
        f.write(f"- Actual rows – Training: {int(train_mask.sum()):,} ({train_mask.sum()/total:.2%})\n")
        f.write(f"- Validation: {int(val_mask.sum()):,} ({val_mask.sum()/total:.2%})\n")
        f.write(f"- Test: {int(test_mask.sum()):,} ({test_mask.sum()/total:.2%})\n")
        f.write("\n---\n\n")
        f.write("## 5. Class distribution per split\n\n")
        f.write("### Training\n\n")
        f.write(fmt_counts(train_counts) + "\n\n")
        f.write("### Validation\n\n")
        f.write(fmt_counts(val_counts) + "\n\n")
        f.write("### Test\n\n")
        f.write(fmt_counts(test_counts) + "\n\n")
        f.write("---\n\n")
        f.write("## 6. Reproducibility\n\n")
        f.write(f"- Random seed used: `{seed}`\n")
        f.write("- Deterministic algorithm; same seed yields identical splits.\n")
        f.write("\n---\n\n")
        f.write("## 7. Limitations\n\n")
        f.write(
            "- Exact per‑class stratification is **not** performed – groups may contain multiple classes, so split proportions per class can deviate.\n"
            "- Conflicting‑label groups are retained; they are reported above.\n"
            "- No resampling or oversampling is performed – class imbalance persists.\n"
        )


def prepare_and_split(
    data_path: Path,
    label_path: Path,
    readme_path: Path,
    output_dir: Path,
    report_path: Path,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """High‑level entry point used by ``scripts/prepare_dataset.py``.
    Returns the three boolean masks.
    """
    df_data, s_label, mapping = load_features_and_labels(data_path, label_path, readme_path)
    group_ids = group_by_exact_features(df_data)
    conflict_df = detect_conflicting_groups(group_ids, s_label)
    group_stats = compute_group_statistics(group_ids, s_label, conflict_df)
    label_counts = s_label.value_counts().to_dict()
    train_mask, val_mask, test_mask = split_groups_groupaware(
        group_ids, s_label, train_frac=train_frac, val_frac=val_frac, test_frac=test_frac, seed=seed
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "train_mask.npy", train_mask)
    np.save(output_dir / "val_mask.npy", val_mask)
    np.save(output_dir / "test_mask.npy", test_mask)
    generate_split_report(
        report_path,
        mapping,
        label_counts,
        conflict_df,
        group_stats,
        (train_mask, val_mask, test_mask),
        train_frac,
        val_frac,
        test_frac,
        seed,
        s_label,
    )
    return train_mask, val_mask, test_mask

if __name__ == "__main__":
    base = Path(__file__).resolve().parents[2]
    data_path = base / "data" / "raw" / "Data.csv"
    label_path = base / "data" / "raw" / "Label.csv"
    readme_path = base / "data" / "raw" / "Readme.txt"
    out_dir = base / "data" / "processed"
    report_path = base / "reports" / "split_report.md"
    prepare_and_split(data_path, label_path, readme_path, out_dir, report_path)
