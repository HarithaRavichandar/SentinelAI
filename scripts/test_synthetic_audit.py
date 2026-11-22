#!/usr/bin/env python3
"""
Synthetic test for cic_audit_and_split.py
Covers:
  - Exact duplicate rows across all 80 columns.
  - Repeated feature vectors with matching labels (same 76 features, different metadata, same label).
  - Conflicting feature vectors with different labels (same 76 features, different labels).
  - Group isolation (all unique rows of a feature group in the exact same split).
  - Correct split row counts and strict invariant verification.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path("H:/SentinelAI")
TEST_DIR = PROJECT_ROOT / "experiments/test_synthetic"
SYNTH_CSV = TEST_DIR / "synthetic.csv"
SYNTH_OUT = TEST_DIR / "output"

METADATA_COLS = ["Dst Port", "Protocol", "Timestamp"]
LABEL_COL = "Label"
EXPECTED_FEATURES = [
    "Flow Duration", "Tot Fwd Pkts", "Tot Bwd Pkts", "TotLen Fwd Pkts", "TotLen Bwd Pkts",
    "Fwd Pkt Len Max", "Fwd Pkt Len Min", "Fwd Pkt Len Mean", "Fwd Pkt Len Std",
    "Bwd Pkt Len Max", "Bwd Pkt Len Min", "Bwd Pkt Len Mean", "Bwd Pkt Len Std",
    "Flow Byts/s", "Flow Pkts/s", "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
    "Fwd IAT Tot", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
    "Bwd IAT Tot", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
    "Fwd PSH Flags", "Bwd PSH Flags", "Fwd URG Flags", "Bwd URG Flags",
    "Fwd Header Len", "Bwd Header Len", "Fwd Pkts/s", "Bwd Pkts/s",
    "Pkt Len Min", "Pkt Len Max", "Pkt Len Mean", "Pkt Len Std", "Pkt Len Var",
    "FIN Flag Cnt", "SYN Flag Cnt", "RST Flag Cnt", "PSH Flag Cnt", "ACK Flag Cnt", "URG Flag Cnt",
    "CWE Flag Count", "ECE Flag Cnt", "Down/Up Ratio", "Pkt Size Avg",
    "Fwd Seg Size Avg", "Bwd Seg Size Avg",
    "Fwd Byts/b Avg", "Fwd Pkts/b Avg", "Fwd Blk Rate Avg",
    "Bwd Byts/b Avg", "Bwd Pkts/b Avg", "Bwd Blk Rate Avg",
    "Subflow Fwd Pkts", "Subflow Fwd Byts", "Subflow Bwd Pkts", "Subflow Bwd Byts",
    "Init Fwd Win Byts", "Init Bwd Win Byts", "Fwd Act Data Pkts", "Fwd Seg Size Min",
    "Active Mean", "Active Std", "Active Max", "Active Min",
    "Idle Mean", "Idle Std", "Idle Max", "Idle Min",
]
HEADER = METADATA_COLS + EXPECTED_FEATURES + [LABEL_COL]


def create_synthetic_dataset():
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True, exist_ok=True)

    rows = []

    def make_feat_vec(base_val):
        return [str(base_val + i) for i in range(76)]

    # Group 1: Feature vector 100
    # Row 1: base row
    f1 = make_feat_vec(100)
    r1 = ["80", "6", "2018-02-15 08:00:00"] + f1 + ["Benign"]
    rows.append(r1)
    # Row 2: EXACT DUPLICATE of Row 1 (all 80 cols identical)
    r2 = list(r1)
    rows.append(r2)
    # Row 3: REPEATED FEATURE VECTOR with MATCHING LABEL (different port & timestamp, same features & label)
    r3 = ["443", "6", "2018-02-15 08:05:00"] + f1 + ["Benign"]
    rows.append(r3)

    # Group 2: Feature vector 200 (CONFLICTING GROUP)
    f2 = make_feat_vec(200)
    # Row 4: Label Benign
    r4 = ["21", "6", "2018-02-15 08:10:00"] + f2 + ["Benign"]
    rows.append(r4)
    # Row 5: Label FTP-BruteForce (conflicting!)
    r5 = ["21", "6", "2018-02-15 08:11:00"] + f2 + ["FTP-BruteForce"]
    rows.append(r5)
    # Row 6: EXACT DUPLICATE of Row 5
    r6 = list(r5)
    rows.append(r6)

    # Groups 3..22: 20 distinct unique groups (base_vals 1000..1019)
    labels_cycle = ["Benign", "FTP-BruteForce", "SSH-Bruteforce"]
    for idx, base in enumerate(range(1000, 1020)):
        lbl = labels_cycle[idx % len(labels_cycle)]
        f = make_feat_vec(base)
        r = [str(1024 + idx), "6", f"2018-02-15 09:{idx:02d}:00"] + f + [lbl]
        rows.append(r)

    with open(SYNTH_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)

    print(f"Created synthetic dataset at {SYNTH_CSV} with {len(rows)} data rows.")
    return len(rows)


def run_pipeline():
    py_exe = r"C:\Users\harit\AppData\Local\Programs\Python\Python313\python.exe"
    script = PROJECT_ROOT / "scripts/cic_audit_and_split.py"
    cmd = [
        py_exe,
        str(script),
        "--csv", str(SYNTH_CSV),
        "--out", str(SYNTH_OUT),
        "--seed", "42",
        "--force",
    ]
    print(f"Executing: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:\n", proc.stdout)
    if proc.stderr:
        print("STDERR:\n", proc.stderr)
    assert proc.returncode == 0, f"Pipeline failed with code {proc.returncode}"


def compute_ground_truth_from_csv(csv_path):
    """
    Independently inspects the synthetic CSV from scratch and calculates
    ground-truth counts without relying on any pipeline code or hardcoded numbers.
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        raw_rows = list(reader)

    total_rows = len(raw_rows)

    # 1. Exact duplicates across all 80 columns
    seen_full_rows = set()
    exact_dup_count = 0
    unique_rows = []
    for r in raw_rows:
        t = tuple(r)
        if t in seen_full_rows:
            exact_dup_count += 1
        else:
            seen_full_rows.add(t)
            unique_rows.append(r)

    unique_row_count = len(unique_rows)
    assert total_rows == exact_dup_count + unique_row_count

    # 2. Group unique rows by 76 feature columns (index 3 to -1)
    feat_groups = {}  # feat_tuple -> list of unique rows
    for r in unique_rows:
        feat_tuple = tuple(r[3:-1])
        feat_groups.setdefault(feat_tuple, []).append(r)

    conflicting_groups = 0
    conflicting_unique_rows = 0
    eligible_groups = 0
    eligible_unique_rows = 0

    for feat_tuple, u_rows in feat_groups.items():
        labels = {r[-1] for r in u_rows}
        if len(labels) > 1:
            conflicting_groups += 1
            conflicting_unique_rows += len(u_rows)
        else:
            eligible_groups += 1
            eligible_unique_rows += len(u_rows)

    # Count total rows in CSV belonging to conflicting groups (including exact dups)
    conflicting_feats = {f for f, u_rows in feat_groups.items() if len({r[-1] for r in u_rows}) > 1}
    conflicting_total_csv_rows = sum(1 for r in raw_rows if tuple(r[3:-1]) in conflicting_feats)

    assert unique_row_count == conflicting_unique_rows + eligible_unique_rows
    assert total_rows == exact_dup_count + conflicting_unique_rows + eligible_unique_rows

    return {
        "total_rows": total_rows,
        "exact_dups": exact_dup_count,
        "unique_rows": unique_row_count,
        "conflicting_groups": conflicting_groups,
        "conflicting_unique_rows": conflicting_unique_rows,
        "conflicting_total_csv_rows": conflicting_total_csv_rows,
        "eligible_groups": eligible_groups,
        "eligible_unique_rows": eligible_unique_rows,
    }


def verify_results(total_csv_rows):
    print("Verifying synthetic audit results against independent ground truth...")

    gt = compute_ground_truth_from_csv(SYNTH_CSV)
    print("Independent Ground Truth:")
    for k, v in gt.items():
        print(f"  {k}: {v}")

    # 1. Check duplicate_rows_removed.json
    dup_file = SYNTH_OUT / "audits/duplicate_rows_removed.json"
    assert dup_file.exists(), "duplicate_rows_removed.json missing"
    with open(dup_file) as f:
        dup_data = json.load(f)
    print("Duplicate data from audit:", dup_data)
    assert dup_data["original_row_count"] == gt["total_rows"]
    assert dup_data["exact_duplicate_rows_removed"] == gt["exact_dups"]
    assert dup_data["unique_rows_after_duplicate_removal"] == gt["unique_rows"]

    # 2. Check conflicting_feature_vectors.csv
    conflict_file = SYNTH_OUT / "audits/conflicting_feature_vectors.csv"
    assert conflict_file.exists(), "conflicting_feature_vectors.csv missing"
    with open(conflict_file) as f:
        reader = csv.reader(f)
        c_header = next(reader)
        c_rows = list(reader)
    print(f"Conflicting rows written to audit CSV: {len(c_rows)}")
    assert len(c_rows) == gt["conflicting_total_csv_rows"], (
        f"Expected {gt['conflicting_total_csv_rows']} conflicting rows, got {len(c_rows)}"
    )

    # 3. Check dataset_validation.json
    val_file = SYNTH_OUT / "audits/dataset_validation.json"
    with open(val_file) as f:
        val_data = json.load(f)
    print("Validation data from audit:", val_data)
    assert val_data["original_row_count"] == gt["total_rows"]
    assert val_data["exact_duplicate_rows_count"] == gt["exact_dups"]
    assert val_data["unique_rows_after_duplicate_removal"] == gt["unique_rows"]
    assert val_data["conflicting_groups_count"] == gt["conflicting_groups"]
    assert val_data["conflicting_unique_rows_count"] == gt["conflicting_unique_rows"]
    assert val_data["conflicting_total_rows_in_csv"] == gt["conflicting_total_csv_rows"]
    assert val_data["eligible_unique_rows_count"] == gt["eligible_unique_rows"]

    # 4. Check Group 1 isolation: r1 and r3 must both be in the SAME split file
    train_csv = SYNTH_OUT / "splits/train.csv"
    val_csv = SYNTH_OUT / "splits/val.csv"
    test_csv = SYNTH_OUT / "splits/test.csv"

    def find_in_csv(path, target_port):
        with open(path) as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row[0] == target_port and row[3] == "100":
                    return True
        return False

    r1_in = {
        "train": find_in_csv(train_csv, "80"),
        "val": find_in_csv(val_csv, "80"),
        "test": find_in_csv(test_csv, "80"),
    }
    r3_in = {
        "train": find_in_csv(train_csv, "443"),
        "val": find_in_csv(val_csv, "443"),
        "test": find_in_csv(test_csv, "443"),
    }
    print(f"Row 1 (port 80) presence: {r1_in}")
    print(f"Row 3 (port 443) presence: {r3_in}")

    split_r1 = [k for k, v in r1_in.items() if v]
    split_r3 = [k for k, v in r3_in.items() if v]
    assert len(split_r1) == 1, f"Row 1 should be in exactly 1 split, got {split_r1}"
    assert len(split_r3) == 1, f"Row 3 should be in exactly 1 split, got {split_r3}"
    assert split_r1 == split_r3, f"Group isolation FAILED: Row 1 in {split_r1}, Row 3 in {split_r3}"
    print(f"SUCCESS: Group 1 (rows 1 and 3) isolated together in split '{split_r1[0]}'.")

    # 5. Check sum of split rows == eligible unique rows
    train_cnt = sum(1 for _ in csv.reader(open(train_csv))) - 1
    val_cnt = sum(1 for _ in csv.reader(open(val_csv))) - 1
    test_cnt = sum(1 for _ in csv.reader(open(test_csv))) - 1
    split_sum = train_cnt + val_cnt + test_cnt
    print(f"Split counts: train={train_cnt}, val={val_cnt}, test={test_cnt}, sum={split_sum}")
    assert split_sum == gt["eligible_unique_rows"], (
        f"Split sum ({split_sum}) != Ground Truth eligible unique rows ({gt['eligible_unique_rows']})"
    )

    print("\nALL SYNTHETIC INVARIANTS INDEPENDENTLY VERIFIED AND PASSED!")


def main():
    total_rows = create_synthetic_dataset()
    run_pipeline()
    verify_results(total_rows)


if __name__ == "__main__":
    main()
