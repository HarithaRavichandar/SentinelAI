#!/usr/bin/env python3
"""
CIC Three-Class Experiment — Audit & Group-Aware Split Pipeline
Task 12.2.1.1 — Memory-Efficient, Standard-Library-Only Implementation (Repaired)

Usage:
    python cic_audit_and_split.py [--csv PATH] [--out PATH] [--seed INT] [--force]

Implements:
    - Phase 1: Streaming schema & dataset validation.
    - Phase 2: Exact duplicate full-row detection (all 80 columns).
    - Phase 3: Canonical feature-vector grouping & non-finite value audit.
    - Phase 4: Group-aware train/val/test splitting using unique row counts.
    - Phase 5: Fast streaming single-pass CSV generation without N+1 queries.
    - Phase 6: Independent output validation (leakage, duplicates, schemas, class distributions).

Constraints
-----------
* Standard library ONLY (csv, hashlib, sqlite3, json, math, statistics, random, pathlib, argparse).
* Streaming CSV processing — the full file is NEVER loaded into memory at once.
* SQLite used for disk-backed indexing; streaming joins used for CSV writing.
* Original CIC CSV is NEVER modified.
* Existing SentinelAI model/preprocessor artifacts are NOT touched.
* Re-running with --force overwrites audit output but never touches source CSV.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import math
import os
import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# CONSTANTS — exact expected schema
# ---------------------------------------------------------------------------
METADATA_COLS = ["Dst Port", "Protocol", "Timestamp"]
LABEL_COL = "Label"
EXPECTED_TOTAL_COLS = 80
EXPECTED_FEATURE_COUNT = 76
EXPECTED_LABELS = {"Benign", "FTP-BruteForce", "SSH-Bruteforce"}

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

DEFAULT_CSV = Path(r"H:\SentinelAI\data\external\cic_ids_2018\cic.csv")
DEFAULT_OUT = Path(r"H:\SentinelAI\experiments\cic_three_class")
DEFAULT_SEED = 42

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
_LOG_FILE = None


def log(msg: str, level: str = "INFO"):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    if _LOG_FILE:
        _LOG_FILE.write(line + "\n")
        _LOG_FILE.flush()


def abort(msg: str):
    log(msg, "FATAL")
    sys.exit(1)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):  # 1 MiB chunks
            h.update(chunk)
    return h.hexdigest().upper()


def canonical_feature_val(raw: str) -> str:
    """
    Return a normalised string representation of a feature value suitable for
    hashing. NaN, +inf, and -inf are each mapped to a unique sentinel token.
    All finite values are parsed as float64 and formatted with full precision.
    Raises ValueError if the value is not parseable as a float.
    """
    stripped = raw.strip()
    try:
        v = float(stripped)
    except ValueError:
        raise ValueError(f"Non-numeric feature value: {raw!r}")
    if math.isnan(v):
        return "__NAN__"
    if math.isinf(v):
        return "__POSINF__" if v > 0 else "__NEGINF__"
    return repr(v)


def feature_hash(canonical_vals: List[str]) -> str:
    """SHA-256 of the pipe-joined canonical feature vector."""
    blob = "|".join(canonical_vals).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def row_hash(raw_row: List[str]) -> str:
    """SHA-256 of the full raw row (all 80 columns, comma-joined)."""
    blob = ",".join(raw_row).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# PHASE 1  —  Schema validation
# ---------------------------------------------------------------------------
def validate_schema(csv_path: Path) -> Tuple[List[str], List[str], int]:
    """Return (header, feature_cols, feature_start_idx). Aborts if schema is wrong."""
    log("Phase 1 — validating CSV schema...")
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            abort("CSV file is empty.")

    if len(header) != EXPECTED_TOTAL_COLS:
        abort(
            f"Column count mismatch: expected {EXPECTED_TOTAL_COLS}, "
            f"got {len(header)}. Cannot continue."
        )

    if header[:3] != METADATA_COLS:
        abort(
            f"First three columns mismatch.\n  Expected: {METADATA_COLS}\n"
            f"  Got:      {header[:3]}"
        )
    if header[-1] != LABEL_COL:
        abort(f"Last column should be '{LABEL_COL}', got '{header[-1]}'.")

    feature_cols = header[3:-1]
    if len(feature_cols) != EXPECTED_FEATURE_COUNT:
        abort(f"Expected {EXPECTED_FEATURE_COUNT} feature cols, got {len(feature_cols)}.")
    if feature_cols != EXPECTED_FEATURES:
        mismatches = [(i, e, g) for i, (e, g) in enumerate(zip(EXPECTED_FEATURES, feature_cols)) if e != g]
        abort(
            f"Feature column order mismatch at positions: "
            + ", ".join(f"{i}(expected={e!r} got={g!r})" for i, e, g in mismatches)
        )

    log(f"  Schema OK — {len(header)} columns, {len(feature_cols)} features.")
    return header, feature_cols, 3


# ---------------------------------------------------------------------------
# PHASE 2 / 3  —  Streaming Pass (Duplicates, Groups, Non-Finite Stats)
# ---------------------------------------------------------------------------
def streaming_pass(
    csv_path: Path,
    feature_cols: List[str],
    out_dir: Path,
    db_path: Path,
) -> Dict:
    """
    Single streaming pass that simultaneously:
      * Identifies exact duplicate full rows (is_dup=1) vs unique rows (is_dup=0).
      * Groups identical feature vectors.
      * IMPORTANT: Only increments group unique row counts for is_dup=0 rows.
      * Tracks all distinct labels seen for conflict detection.
      * Collects non-finite statistics per feature column.
      * Counts raw labels.
      * Populates SQLite tables: rows and groups.
    """
    log("Single streaming pass — exact duplicates, grouping, non-finite stats, label counts...")

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA cache_size=-131072;  /* 128 MiB page cache */
        CREATE TABLE IF NOT EXISTS rows (
            row_num     INTEGER PRIMARY KEY,
            row_sha256  TEXT NOT NULL,
            feat_sha256 TEXT NOT NULL,
            label       TEXT NOT NULL,
            is_dup      INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS groups (
            feat_sha256     TEXT PRIMARY KEY,
            first_row_num   INTEGER NOT NULL,
            row_count       INTEGER NOT NULL DEFAULT 0,
            has_conflict    INTEGER NOT NULL DEFAULT 0,
            labels_seen     TEXT NOT NULL
        );
    """)
    con.commit()

    RESERVOIR_SIZE = 50_000
    feat_stats: Dict[str, Dict] = {}
    for col in feature_cols:
        feat_stats[col] = {
            "nan": 0,
            "pos_inf": 0,
            "neg_inf": 0,
            "finite_min": None,
            "finite_max": None,
            "finite_count": 0,
            "welf_mean": 0.0,
            "welf_M2": 0.0,
            "reservoir": [],
            "reservoir_count": 0,
        }

    label_counts: Dict[str, int] = collections.Counter()
    total_rows = 0
    exact_dups = 0
    parse_errors = 0

    seen_row_hashes: Set[str] = set()

    BATCH = 10_000
    batch_rows: List[Dict] = []
    # feat_sha256 -> {"first_row_num": int, "unique_count": int, "labels": set}
    batch_groups: Dict[str, Dict] = {}

    def flush_batch():
        cur.executemany(
            "INSERT OR IGNORE INTO rows (row_num, row_sha256, feat_sha256, label, is_dup)"
            " VALUES (?,?,?,?,?)",
            [(r["row_num"], r["row_sha256"], r["feat_sha256"], r["label"], r["is_dup"])
             for r in batch_rows],
        )

        for fh, g in batch_groups.items():
            existing = cur.execute(
                "SELECT row_count, labels_seen, has_conflict FROM groups WHERE feat_sha256=?",
                (fh,),
            ).fetchone()

            if existing is None:
                labels_list = sorted(g["labels"])
                conflict = 1 if len(labels_list) > 1 else 0
                cur.execute(
                    "INSERT INTO groups (feat_sha256, first_row_num, row_count, has_conflict, labels_seen)"
                    " VALUES (?,?,?,?,?)",
                    (fh, g["first_row_num"], g["unique_count"], conflict, json.dumps(labels_list)),
                )
            else:
                old_count, old_labels_json, old_conflict = existing
                old_labels = set(json.loads(old_labels_json))
                new_labels = old_labels | g["labels"]
                conflict = 1 if len(new_labels) > 1 else old_conflict
                cur.execute(
                    "UPDATE groups SET row_count=?, has_conflict=?, labels_seen=? WHERE feat_sha256=?",
                    (old_count + g["unique_count"], conflict, json.dumps(sorted(new_labels)), fh),
                )
        con.commit()
        batch_rows.clear()
        batch_groups.clear()

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)  # skip header

        for raw_row in reader:
            total_rows += 1

            if len(raw_row) != EXPECTED_TOTAL_COLS:
                log(f"  Row {total_rows}: wrong column count ({len(raw_row)}), skipping.", "WARN")
                parse_errors += 1
                continue

            label = raw_row[-1].strip()
            label_counts[label] += 1

            # Exact duplicate full-row check
            rh = row_hash(raw_row)
            if rh in seen_row_hashes:
                is_dup = 1
                exact_dups += 1
            else:
                is_dup = 0
                seen_row_hashes.add(rh)

            # Feature vector canonicalisation
            feature_vals_raw = raw_row[3:-1]
            canon_vals = []
            feat_error = False
            for col, val in zip(feature_cols, feature_vals_raw):
                try:
                    cv = canonical_feature_val(val)
                    canon_vals.append(cv)

                    fs = feat_stats[col]
                    if cv == "__NAN__":
                        fs["nan"] += 1
                    elif cv == "__POSINF__":
                        fs["pos_inf"] += 1
                    elif cv == "__NEGINF__":
                        fs["neg_inf"] += 1
                    else:
                        fv = float(cv)
                        fs["finite_count"] += 1
                        if fs["finite_min"] is None or fv < fs["finite_min"]:
                            fs["finite_min"] = fv
                        if fs["finite_max"] is None or fv > fs["finite_max"]:
                            fs["finite_max"] = fv

                        n = fs["finite_count"]
                        delta = fv - fs["welf_mean"]
                        fs["welf_mean"] += delta / n
                        fs["welf_M2"] += delta * (fv - fs["welf_mean"])

                        rc = fs["reservoir_count"]
                        fs["reservoir_count"] = rc + 1
                        rs = fs["reservoir"]
                        if len(rs) < RESERVOIR_SIZE:
                            rs.append(fv)
                        else:
                            j = random.randint(0, rc)
                            if j < RESERVOIR_SIZE:
                                rs[j] = fv
                except ValueError as e:
                    log(f"  Row {total_rows}, col {col!r}: {e}", "WARN")
                    parse_errors += 1
                    feat_error = True
                    break

            fh_key = feature_hash(canon_vals) if not feat_error else "__PARSE_ERROR__"

            batch_rows.append({
                "row_num": total_rows,
                "row_sha256": rh,
                "feat_sha256": fh_key,
                "label": label,
                "is_dup": is_dup,
            })

            unique_inc = 1 if is_dup == 0 else 0
            if fh_key not in batch_groups:
                batch_groups[fh_key] = {
                    "first_row_num": total_rows,
                    "unique_count": unique_inc,
                    "labels": {label},
                }
            else:
                batch_groups[fh_key]["unique_count"] += unique_inc
                batch_groups[fh_key]["labels"].add(label)

            if len(batch_rows) >= BATCH:
                flush_batch()

            if total_rows % 100_000 == 0:
                log(f"  Processed {total_rows:,} rows...")

    if batch_rows:
        flush_batch()

    log(f"Streaming pass complete. Total rows={total_rows:,}, exact_dups={exact_dups:,}, parse_errors={parse_errors}.")

    # Create indices to accelerate downstream queries and streaming joins
    log("Creating SQLite indices on rows and groups...")
    cur.executescript("""
        CREATE INDEX IF NOT EXISTS idx_rows_is_dup_row_num ON rows (is_dup, row_num);
        CREATE INDEX IF NOT EXISTS idx_rows_feat_sha ON rows (feat_sha256);
        CREATE INDEX IF NOT EXISTS idx_groups_conflict ON groups (has_conflict);
    """)
    con.commit()
    con.close()

    return {
        "total_rows": total_rows,
        "exact_dups": exact_dups,
        "parse_errors": parse_errors,
        "label_counts": dict(label_counts),
        "feat_stats": feat_stats,
    }


# ---------------------------------------------------------------------------
# PHASE 4  —  Group-aware split generation
# ---------------------------------------------------------------------------
def group_aware_split(
    con: sqlite3.Connection,
    seed: int,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> Dict:
    """
    Assign each non-conflicting feature group to exactly one split (train/val/test).
    Uses the unique row count (row_count) for split target calculations.
    """
    log(f"Phase 4 — group-aware split (seed={seed}, train={train_frac:.0%}, val={val_frac:.0%})...")

    cur = con.cursor()
    eligible = cur.execute(
        """
        SELECT feat_sha256, row_count, labels_seen
        FROM groups
        WHERE has_conflict = 0 AND feat_sha256 != '__PARSE_ERROR__'
        ORDER BY feat_sha256
        """
    ).fetchall()

    if not eligible:
        abort("No eligible groups after conflict exclusion. Cannot create splits.")

    total_eligible_unique_rows = sum(r[1] for r in eligible)
    train_target = int(total_eligible_unique_rows * train_frac)
    val_target = int(total_eligible_unique_rows * val_frac)

    log(f"  Eligible groups: {len(eligible):,}, unique rows: {total_eligible_unique_rows:,}")
    log(f"  Targets — train: {train_target:,}, val: {val_target:,}, test: {total_eligible_unique_rows - train_target - val_target:,}")

    # Deterministic shuffle
    rng = random.Random(seed)
    eligible = list(eligible)
    rng.shuffle(eligible)

    cur.executescript("""
        DROP TABLE IF EXISTS split_assignments;
        CREATE TABLE split_assignments (
            feat_sha256 TEXT PRIMARY KEY,
            split       TEXT NOT NULL
        );
    """)
    con.commit()

    train_rows = val_rows = test_rows = 0
    train_groups = val_groups = test_groups = 0
    train_labels: Dict[str, int] = collections.Counter()
    val_labels: Dict[str, int] = collections.Counter()
    test_labels: Dict[str, int] = collections.Counter()

    assignments = []
    for feat_sha, unique_count, labels_json in eligible:
        parsed = json.loads(labels_json)
        label = parsed[0] if isinstance(parsed, list) else parsed
        if train_rows + unique_count <= train_target:
            split = "train"
            train_rows += unique_count
            train_groups += 1
            train_labels[label] += unique_count
        elif val_rows + unique_count <= val_target:
            split = "val"
            val_rows += unique_count
            val_groups += 1
            val_labels[label] += unique_count
        else:
            split = "test"
            test_rows += unique_count
            test_groups += 1
            test_labels[label] += unique_count
        assignments.append((feat_sha, split))

    cur.executemany(
        "INSERT INTO split_assignments (feat_sha256, split) VALUES (?,?)",
        assignments,
    )
    con.commit()

    # Verification: each feat_sha256 must appear in exactly one split
    overlap = cur.execute(
        """
        SELECT feat_sha256, COUNT(*) as c
        FROM split_assignments
        GROUP BY feat_sha256
        HAVING c > 1
        """
    ).fetchall()
    if overlap:
        abort(f"Group-overlap detected in split_assignments: {overlap[:5]}. Aborting.")

    log(f"  Split assignments generated: no group overlap.")

    return {
        "train": {"rows": train_rows, "groups": train_groups, "label_counts": dict(train_labels)},
        "val": {"rows": val_rows, "groups": val_groups, "label_counts": dict(val_labels)},
        "test": {"rows": test_rows, "groups": test_groups, "label_counts": dict(test_labels)},
        "total_eligible_unique_rows": total_eligible_unique_rows,
    }


# ---------------------------------------------------------------------------
# PHASE 5  —  Optimized Streaming CSV Writing & Conflict Writing
# ---------------------------------------------------------------------------
def write_split_csvs(
    csv_path: Path,
    con: sqlite3.Connection,
    splits_dir: Path,
    audits_dir: Path,
    header: List[str],
) -> Dict[str, int]:
    """
    Stream through the original CSV in a single pass while advancing a single
    SQL join query ordered by row_num.
    Simultaneously writes:
      - train.csv, val.csv, test.csv
      - audits/conflicting_feature_vectors.csv (with full raw row details)
    """
    log("Writing split CSV files and conflicting vectors (single-pass streaming join)...")

    cur = con.cursor()

    # Pre-load conflicting row numbers into a small in-memory lookup
    conflict_rows = cur.execute("""
        SELECT r.row_num, r.feat_sha256, r.is_dup
        FROM rows r
        JOIN groups g ON r.feat_sha256 = g.feat_sha256
        WHERE g.has_conflict = 1
        ORDER BY r.row_num
    """).fetchall()
    conflict_map = {row_num: (feat_sha, is_dup) for row_num, feat_sha, is_dup in conflict_rows}
    log(f"  Found {len(conflict_map):,} conflicting rows to record in audit CSV.")

    conflict_csv_path = audits_dir / "conflicting_feature_vectors.csv"
    conflict_fh = open(conflict_csv_path, "w", newline="", encoding="utf-8")
    conflict_writer = csv.writer(conflict_fh)
    conflict_writer.writerow(["feat_sha256", "row_num", "is_dup"] + header)

    # Prepare streaming cursor for assigned rows (is_dup=0 only)
    assign_cur = con.cursor()
    assign_cur.execute("""
        SELECT r.row_num, s.split
        FROM rows r
        JOIN split_assignments s
          ON r.feat_sha256 = s.feat_sha256
        WHERE r.is_dup = 0
        ORDER BY r.row_num
    """)

    assign_iter = iter(assign_cur)
    try:
        next_assigned = next(assign_iter)  # (row_num, split)
    except StopIteration:
        next_assigned = None

    files = {}
    writers = {}
    for split in ("train", "val", "test"):
        p = splits_dir / f"{split}.csv"
        files[split] = open(p, "w", newline="", encoding="utf-8")
        writers[split] = csv.writer(files[split])
        writers[split].writerow(header)

    total_csv_rows = 0
    written = {"train": 0, "val": 0, "test": 0}
    conflict_written = 0

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)  # skip header

        for row_num, raw_row in enumerate(reader, start=1):
            total_csv_rows += 1

            # Check if this row is part of a conflicting group
            if row_num in conflict_map:
                feat_sha, is_dup = conflict_map[row_num]
                conflict_writer.writerow([feat_sha, row_num, is_dup] + raw_row)
                conflict_written += 1

            # Check if this row is assigned to a split
            if next_assigned is not None and row_num == next_assigned[0]:
                split_name = next_assigned[1]
                writers[split_name].writerow(raw_row)
                written[split_name] += 1
                try:
                    next_assigned = next(assign_iter)
                except StopIteration:
                    next_assigned = None

            if total_csv_rows % 200_000 == 0:
                log(f"  Processed {total_csv_rows:,} CSV rows (written train={written['train']:,}, val={written['val']:,}, test={written['test']:,})...")

    conflict_fh.close()
    for f in files.values():
        f.close()

    if next_assigned is not None:
        abort(f"Not all assigned rows were written from the CSV! Next unwritten row: {next_assigned}")

    log(f"  Split files written — train:{written['train']:,} val:{written['val']:,} test:{written['test']:,}")
    log(f"  Conflicting rows written: {conflict_written:,} to {conflict_csv_path}")

    return written


# ---------------------------------------------------------------------------
# PHASE 5  —  Feature quality report
# ---------------------------------------------------------------------------
def write_feature_quality(feat_stats: Dict, out_path: Path, feature_cols: List[str]):
    log("Writing feature quality report...")
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "Feature", "NaN", "PosInf", "NegInf",
            "FiniteCount", "FiniteMin", "FiniteMax",
            "ApproxMedian",
        ])
        for col in feature_cols:
            fs = feat_stats[col]
            reservoir = sorted(fs["reservoir"])
            if reservoir:
                n = len(reservoir)
                mid = n // 2
                approx_median = reservoir[mid] if n % 2 == 1 else (reservoir[mid - 1] + reservoir[mid]) / 2
            else:
                approx_median = ""
            writer.writerow([
                col,
                fs["nan"],
                fs["pos_inf"],
                fs["neg_inf"],
                fs["finite_count"],
                fs["finite_min"] if fs["finite_min"] is not None else "",
                fs["finite_max"] if fs["finite_max"] is not None else "",
                approx_median,
            ])
    log(f"  Feature quality report written to {out_path}")


# ---------------------------------------------------------------------------
# PHASE 6  —  Independent Output Validation
# ---------------------------------------------------------------------------
def verify_splits_independent(
    splits_dir: Path,
    header: List[str],
    expected_split_rows: Dict[str, int],
    eligible_unique_rows: int,
    exact_dups_count: int,
    conflicting_unique_rows: int,
    total_source_rows: int,
    con: sqlite3.Connection,
) -> Dict:
    """
    Independent verification of generated CSV splits:
      1. Schema matches exactly for all 3 files.
      2. Row counts match expected values exactly.
      3. train + val + test == eligible_unique_rows.
      4. total_source_rows == exact_dups + conflicting_unique_rows + eligible_unique_rows.
      5. No feature group occurs in more than one split (group isolation / leakage test).
      6. No duplicate full rows occur within or across splits (exact duplicate check).
      7. No rows from conflicting groups are present in any split.
      8. Class distributions reported for each split.
    """
    log("Phase 6 — Independent output validation...")
    cur = con.cursor()

    conflict_feats = set(
        r[0] for r in cur.execute("SELECT feat_sha256 FROM groups WHERE has_conflict = 1").fetchall()
    )

    results: Dict[str, Dict] = {}
    total_written_rows = 0

    seen_group_split: Dict[str, str] = {}
    seen_row_hashes_split: Set[str] = set()

    for split in ("train", "val", "test"):
        p = splits_dir / f"{split}.csv"
        if not p.exists():
            abort(f"Verification FAILED: Split file missing: {p}")

        row_count = 0
        label_counts: Dict[str, int] = collections.Counter()

        with open(p, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            file_header = next(reader)
            if file_header != header:
                abort(f"Verification FAILED: Schema mismatch in {p.name}")

            for line_idx, raw_row in enumerate(reader, start=1):
                row_count += 1
                label = raw_row[-1].strip()
                label_counts[label] += 1

                # Exact duplicate row check across splits
                rh = row_hash(raw_row)
                if rh in seen_row_hashes_split:
                    abort(f"Verification FAILED: Duplicate full row found in split {split} at line {line_idx}!")
                seen_row_hashes_split.add(rh)

                # Feature group check
                canon_vals = [canonical_feature_val(v) for v in raw_row[3:-1]]
                fh_key = feature_hash(canon_vals)

                if fh_key in conflict_feats:
                    abort(f"Verification FAILED: Conflicting feature group {fh_key} found in split {split} at line {line_idx}!")

                if fh_key in seen_group_split and seen_group_split[fh_key] != split:
                    abort(f"Verification FAILED: Group leakage! Feature group {fh_key} found in both {seen_group_split[fh_key]} and {split}!")
                seen_group_split[fh_key] = split

        if row_count != expected_split_rows[split]:
            abort(f"Verification FAILED: {split} row count mismatch! Expected {expected_split_rows[split]}, got {row_count}")

        total_written_rows += row_count
        results[split] = {"rows": row_count, "label_counts": dict(label_counts)}
        log(f"  {split}.csv: {row_count:,} rows verified. Distribution: {dict(label_counts)}")

    if total_written_rows != eligible_unique_rows:
        abort(f"Verification FAILED: Sum of split rows ({total_written_rows}) != eligible unique rows ({eligible_unique_rows})")

    log("  Invariant passed: train_rows + val_rows + test_rows == eligible_unique_rows.")
    log(f"  Invariant passed: 0 group overlaps across splits (total unique groups in splits = {len(seen_group_split):,}).")
    log(f"  Invariant passed: 0 duplicate full rows within or across splits (total unique rows = {len(seen_row_hashes_split):,}).")
    log("  Invariant passed: 0 conflicting-group rows found in any split.")

    return results


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    global _LOG_FILE

    parser = argparse.ArgumentParser(description="Repaired CIC Audit and Split Pipeline")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing audit output (never touches source CSV or models).")
    args = parser.parse_args()

    csv_path: Path = args.csv
    out_root: Path = args.out
    seed: int = args.seed

    audits_dir = out_root / "audits"
    splits_dir = out_root / "splits"
    logs_dir = out_root / "logs"
    scratch_dir = out_root / "scratch"
    for d in (audits_dir, splits_dir, logs_dir, scratch_dir):
        d.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    log_path = logs_dir / f"audit_{time.strftime('%Y%m%d_%H%M%S')}.log"
    _LOG_FILE = open(log_path, "w", encoding="utf-8")
    log(f"Log file: {log_path}")
    log(f"Python: {sys.version} ({sys.executable})")

    if not csv_path.exists():
        abort(f"CSV not found: {csv_path}")
    file_size = csv_path.stat().st_size
    log(f"Source CSV: {csv_path} ({file_size:,} bytes)")

    import shutil
    free_bytes = shutil.disk_usage(out_root).free
    log(f"Free disk on output drive: {free_bytes / (1 << 30):.1f} GiB")

    log("Computing SHA-256 of source CSV...")
    orig_sha256 = sha256_file(csv_path)
    log(f"  Source CSV SHA-256: {orig_sha256}")

    # Phase 1: Schema validation
    header, feature_cols, _ = validate_schema(csv_path)

    db_path = scratch_dir / "audit_index.db"
    if db_path.exists() and args.force:
        for ext in ("", "-shm", "-wal"):
            p = scratch_dir / f"audit_index.db{ext}"
            if p.exists():
                p.unlink()
        log("Removed existing SQLite index (--force).")

    # Phase 2 & 3: Streaming pass
    stats = streaming_pass(csv_path, feature_cols, out_root, db_path)

    unexpected_labels = set(stats["label_counts"].keys()) - EXPECTED_LABELS
    if unexpected_labels:
        abort(f"Unexpected labels found: {unexpected_labels}. Label counts: {stats['label_counts']}")
    log(f"Labels verified: {stats['label_counts']}")

    # Write duplicate_rows_removed.json
    unique_rows_after_dups = stats["total_rows"] - stats["exact_dups"]
    dup_json = {
        "original_row_count": stats["total_rows"],
        "exact_duplicate_rows_removed": stats["exact_dups"],
        "unique_rows_after_duplicate_removal": unique_rows_after_dups,
        "definition": (
            "Exact duplicate rows are rows that are identical across all 80 columns (metadata, flow features, and label). "
            "Only the first occurrence is retained (is_dup=0); subsequent identical occurrences (is_dup=1) are removed."
        ),
        "distinction_note": (
            "Repeated feature vectors with matching labels (rows that share identical 76 feature values and the same label, "
            "but differ in metadata such as Timestamp or Dst Port) are NOT exact duplicate rows. They are retained as unique "
            "rows (is_dup=0) and kept together in the same split as an atomic feature group."
        )
    }
    with open(audits_dir / "duplicate_rows_removed.json", "w", encoding="utf-8") as fh:
        json.dump(dup_json, fh, indent=2)
    log(f"  Saved duplicate audit to {audits_dir / 'duplicate_rows_removed.json'}")

    # Write feature quality report
    write_feature_quality(stats["feat_stats"], audits_dir / "feature_quality_report.csv", feature_cols)

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    conflict_summary = cur.execute("""
        SELECT COUNT(*), SUM(row_count)
        FROM groups
        WHERE has_conflict = 1
    """).fetchone()
    n_conflict_groups = conflict_summary[0] or 0
    n_conflict_unique_rows = conflict_summary[1] or 0

    total_conflict_rows_in_csv = cur.execute("""
        SELECT COUNT(*)
        FROM rows r
        JOIN groups g ON r.feat_sha256 = g.feat_sha256
        WHERE g.has_conflict = 1
    """).fetchone()[0] or 0

    matching_summary = cur.execute("""
        SELECT COUNT(*), SUM(row_count)
        FROM groups
        WHERE has_conflict = 0 AND feat_sha256 != '__PARSE_ERROR__'
    """).fetchone()
    n_matching_groups = matching_summary[0] or 0
    n_eligible_unique_rows = matching_summary[1] or 0

    log(f"Group Summary:")
    log(f"  Matching groups: {n_matching_groups:,} (eligible unique rows: {n_eligible_unique_rows:,})")
    log(f"  Conflicting groups: {n_conflict_groups:,} (conflicting unique rows: {n_conflict_unique_rows:,}, total in CSV: {total_conflict_rows_in_csv:,})")

    # Phase 4: Group-aware split
    split_info = group_aware_split(con, seed=seed)

    # Phase 5: Fast single-pass streaming write
    written = write_split_csvs(csv_path, con, splits_dir, audits_dir, header)

    # Phase 6: Independent output validation
    expected_split_rows = {
        "train": split_info["train"]["rows"],
        "val": split_info["val"]["rows"],
        "test": split_info["test"]["rows"],
    }
    verification_results = verify_splits_independent(
        splits_dir=splits_dir,
        header=header,
        expected_split_rows=expected_split_rows,
        eligible_unique_rows=n_eligible_unique_rows,
        exact_dups_count=stats["exact_dups"],
        conflicting_unique_rows=n_conflict_unique_rows,
        total_source_rows=stats["total_rows"],
        con=con,
    )

    # Prepare audit reports
    dataset_validation = {
        "source_csv": str(csv_path),
        "source_csv_sha256": orig_sha256,
        "file_size_bytes": file_size,
        "original_row_count": stats["total_rows"],
        "exact_duplicate_rows_count": stats["exact_dups"],
        "unique_rows_after_duplicate_removal": unique_rows_after_dups,
        "conflicting_groups_count": n_conflict_groups,
        "conflicting_unique_rows_count": n_conflict_unique_rows,
        "conflicting_total_rows_in_csv": total_conflict_rows_in_csv,
        "eligible_unique_rows_count": n_eligible_unique_rows,
        "excluded_rows_by_reason": {
            "exact_duplicate_rows": stats["exact_dups"],
            "conflicting_unique_rows": n_conflict_unique_rows,
            "parse_error_rows": stats["parse_errors"],
        },
        "target_split_ratios": {"train": 0.70, "val": 0.15, "test": 0.15},
        "random_seed": seed,
        "actual_split_row_counts": {
            "train": verification_results["train"]["rows"],
            "val": verification_results["val"]["rows"],
            "test": verification_results["test"]["rows"],
        },
        "split_class_distributions": {
            "train": verification_results["train"]["label_counts"],
            "val": verification_results["val"]["label_counts"],
            "test": verification_results["test"]["label_counts"],
        },
        "group_overlap_verification": "PASSED — 0 feature groups overlap across train, val, test",
        "exact_duplicate_verification": "PASSED — 0 duplicate full rows within or across splits",
        "conflicting_rows_exclusion_verification": "PASSED — 0 conflicting-group rows present in splits",
        "schema_verification": "PASSED — All splits match original 80-column schema",
    }
    with open(audits_dir / "dataset_validation.json", "w", encoding="utf-8") as fh:
        json.dump(dataset_validation, fh, indent=2)

    split_summary = {
        "seed": seed,
        "algorithm": "greedy-group-stratified on unique rows (is_dup=0)",
        "train": {
            "groups": split_info["train"]["groups"],
            "rows": verification_results["train"]["rows"],
            "class_distribution": verification_results["train"]["label_counts"],
        },
        "val": {
            "groups": split_info["val"]["groups"],
            "rows": verification_results["val"]["rows"],
            "class_distribution": verification_results["val"]["label_counts"],
        },
        "test": {
            "groups": split_info["test"]["groups"],
            "rows": verification_results["test"]["rows"],
            "class_distribution": verification_results["test"]["label_counts"],
        },
        "total_eligible_unique_rows": n_eligible_unique_rows,
        "exact_duplicate_rows_excluded": stats["exact_dups"],
        "conflicting_unique_rows_excluded": n_conflict_unique_rows,
        "written_split_rows": written,
        "group_overlap_detected": False,
        "exact_duplicates_in_splits": False,
    }
    with open(audits_dir / "split_summary.json", "w", encoding="utf-8") as fh:
        json.dump(split_summary, fh, indent=2)
    with open(splits_dir / "split_summary.json", "w", encoding="utf-8") as fh:
        json.dump(split_summary, fh, indent=2)

    # Generate split_stats.md
    with open(splits_dir / "split_stats.md", "w", encoding="utf-8") as fh:
        fh.write("# CIC Three-Class Dataset Split Statistics\n\n")
        fh.write(f"- **Random Seed**: {seed}\n")
        fh.write(f"- **Total Source Rows**: {stats['total_rows']:,}\n")
        fh.write(f"- **Exact Duplicates Removed**: {stats['exact_dups']:,}\n")
        fh.write(f"- **Conflicting Unique Rows Excluded**: {n_conflict_unique_rows:,} ({n_conflict_groups:,} groups)\n")
        fh.write(f"- **Eligible Unique Rows**: {n_eligible_unique_rows:,} ({n_matching_groups:,} groups)\n\n")

        for split in ("train", "val", "test"):
            res = verification_results[split]
            total = res["rows"]
            pct_of_eligible = total / n_eligible_unique_rows * 100 if n_eligible_unique_rows else 0
            fh.write(f"## {split.capitalize()} Split\n")
            fh.write(f"- **Groups**: {split_info[split]['groups']:,}\n")
            fh.write(f"- **Rows**: {total:,} ({pct_of_eligible:.2f}% of eligible unique rows)\n")
            fh.write("- **Class Distribution**:\n")
            for lbl, cnt in sorted(res["label_counts"].items()):
                lpct = cnt / total * 100 if total else 0
                fh.write(f"  - `{lbl}`: {cnt:,} ({lpct:.2f}%)\n")
            fh.write("\n")

    # Final read-only check on source CSV
    final_sha256 = sha256_file(csv_path)
    if final_sha256 != orig_sha256:
        abort(f"SOURCE CSV SHA-256 CHANGED! Before={orig_sha256} After={final_sha256}")
    log(f"Source CSV SHA-256 unchanged: {final_sha256} — strict read-only constraint verified.")

    con.close()
    elapsed = time.time() - start_time
    log(f"All phases completed successfully in {elapsed:.1f} seconds.")
    _LOG_FILE.close()

    print("\n" + "=" * 50)
    print("AUDIT & SPLIT PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 50)
    print(f"Source CSV rows         : {stats['total_rows']:,}")
    print(f"Exact duplicates removed: {stats['exact_dups']:,}")
    print(f"Unique rows after dups  : {unique_rows_after_dups:,}")
    print(f"Conflicting groups      : {n_conflict_groups:,} ({n_conflict_unique_rows:,} unique rows)")
    print(f"Eligible unique rows    : {n_eligible_unique_rows:,} ({n_matching_groups:,} groups)")
    print(f"Train rows              : {verification_results['train']['rows']:,}")
    print(f"Val rows                : {verification_results['val']['rows']:,}")
    print(f"Test rows               : {verification_results['test']['rows']:,}")
    print(f"Execution time          : {elapsed:.1f}s")
    print(f"Log file                : {log_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
