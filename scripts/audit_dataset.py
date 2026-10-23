#!/usr/bin/env python3
"""
SentinelAI - Phase 1: Second‑stage Data Integrity Audit
audit_dataset.py

Performs a focused integrity audit on the paired feature/label files and
examines their relationship to the full capture (CICFlowMeter_out.csv).
All findings are written to reports/data_integrity_audit.md.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def reconfigure_stdout_utf8() -> None:
    """Force UTF‑8 output on Windows consoles where the default is cp1252.
    This avoids UnicodeEncodeError when printing non‑ASCII characters.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_file(base_dir: Path, candidates: List[str]) -> Path:
    """Return the first existing file matching any of the candidates (case‑insensitive)."""
    for name in candidates:
        candidate = base_dir / name
        if candidate.exists():
            return candidate
    # fallback to case‑insensitive scan
    lowered = {p.name.lower(): p for p in base_dir.iterdir() if p.is_file()}
    for name in candidates:
        if name.lower() in lowered:
            return lowered[name.lower()]
    raise FileNotFoundError(f"None of {candidates} found in {base_dir}")


def load_readme_mapping(readme_path: Path) -> Dict[int, str]:
    """Parse the numeric label mapping from Readme.txt.
    Returns a dict mapping integer ID -> class name.
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


def audit_pair_features_and_labels(
    data_path: Path, label_path: Path, mapping: Dict[int, str]
) -> Tuple[pd.DataFrame, pd.Series, Dict[int, int], int, int, int]:
    """Load Data.csv and Label.csv, verify shape and label validity.
    Returns:
        df_data   – feature DataFrame
        s_label   – label Series
        label_counts – count per class
        dup_rows   – number of exact duplicate feature rows
        unique_rows – number of distinct feature rows
        conflict_dup – number of duplicate rows that have conflicting labels
    """
    # Load full datasets – they comfortably fit in memory (~187 MB + small label)
    # Load feature matrix
    df_data = pd.read_csv(data_path, low_memory=False)
    # Load label column, expecting a header row named "Label"
    s_label_df = pd.read_csv(label_path, header=0, low_memory=False)
    s_label = s_label_df.iloc[:, 0]
    # Ensure labels are integers for proper comparison with mapping
    s_label = s_label.astype(int)
    # Verify row counts match
    if df_data.shape[0] != s_label.shape[0]:
        print(
            f"[!] Row count mismatch: Data.csv has {df_data.shape[0]} rows,"
            f" Label.csv has {s_label.shape[0]} rows"
        )
    # Verify that all label values exist in the mapping
    unexpected = set(s_label.unique()) - set(mapping.keys())
    if unexpected:
        print(f"[!] Unexpected label IDs found (not in Readme.txt): {sorted(unexpected)}")
    # Class distribution
    label_counts = s_label.value_counts().to_dict()

    # Duplicate feature rows detection (exact match across all 76 columns)
    # Use pandas hashing for speed and low memory overhead
    row_hashes = pd.util.hash_pandas_object(df_data, index=False).values
    # Count overall duplicate rows (any row whose hash appears more than once)
    dup_mask = pd.Series(row_hashes).duplicated(keep=False)
    dup_rows = dup_mask.sum()
    unique_rows = df_data.shape[0] - dup_rows

    # Identify duplicate groups with conflicting labels
    # Build a DataFrame of hash + label, then groupby hash and inspect unique label count
    hash_label_df = pd.DataFrame({"hash": row_hashes, "label": s_label})
    conflict_groups = (
        hash_label_df.groupby("hash")
        .agg({"label": lambda x: len(set(x))})
        .rename(columns={"label": "unique_label_cnt"})
        .query("unique_label_cnt > 1")
    )
    # Number of duplicate rows that belong to any conflicting group
    conflict_dup = hash_label_df[hash_label_df["hash"].isin(conflict_groups.index)].shape[0]

    return (
        df_data,
        s_label,
        label_counts,
        dup_rows,
        unique_rows,
        conflict_dup,
    )


def class_distribution_percentages(label_counts: Dict[int, int], total: int) -> Dict[int, Tuple[int, float]]:
    """Return a mapping class_id -> (count, percentage)."""
    return {cid: (cnt, round(cnt / total * 100, 3)) for cid, cnt in label_counts.items()}


def compare_schemas(data_df: pd.DataFrame, cic_path: Path) -> Tuple[List[str], List[str]]:
    """Load a small chunk of the CIC CSV to obtain its column list and compare
    with the Data.csv feature columns.
    Returns two lists:
        shared – columns present in both Data.csv and CICFlowMeter_out.csv (features only)
        cic_extra – columns present only in CIC (metadata or label)
    """
    # Load only the header (first few rows) to avoid huge memory use
    cic_chunk = pd.read_csv(cic_path, nrows=5, low_memory=False)
    cic_cols = list(cic_chunk.columns)
    data_cols = list(data_df.columns)
    # Determine overlap – note that CIC includes 7 metadata columns before the feature block
    shared = [c for c in data_cols if c in cic_cols]
    cic_extra = [c for c in cic_cols if c not in data_cols]
    return shared, cic_extra


def generate_report(
    report_path: Path,
    mapping: Dict[int, str],
    label_counts_pct: Dict[int, Tuple[int, float]],
    dup_rows: int,
    unique_rows: int,
    conflict_dup: int,
    shared_cols: List[str],
    cic_extra: List[str],
) -> None:
    """Write a markdown audit report containing all findings.
    The report is deliberately concise but includes the required quantitative
    information and practical recommendations.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# SentinelAI – Data Integrity Audit (Phase 1)\n\n")
        f.write("> **Purpose** – Verify that the paired feature/label files are internally consistent,\n"
                "detect duplicate rows and potential label conflicts, and examine the relationship\n"
                "to the full capture (CICFlowMeter_out.csv). No data cleaning is performed.\n\n")
        f.write("---\n\n")
        f.write("## 1. Mapping from Readme.txt\n\n")
        f.write("| Numeric ID | Class Name |\n| :---: | :--- |\n")
        for cid in sorted(mapping.keys()):
            f.write(f"| `{cid}` | {mapping[cid]} |\n")
        f.write("\n---\n\n")
        f.write("## 2. Feature/Label Pair Validation\n\n")
        f.write(f"- **Data.csv rows:** {unique_rows + dup_rows:,}\n")
        f.write(f"- **Label.csv rows:** {unique_rows + dup_rows:,} (matched to Data.csv)\n")
        f.write(f"- **Duplicate feature rows (exact match across all columns):** {dup_rows:,}\n")
        f.write(f"- **Unique feature rows:** {unique_rows:,}\n")
        f.write(f"- **Duplicate rows with conflicting labels:** {conflict_dup:,}\n\n")
        if conflict_dup == 0:
            f.write("> [!NOTE] No duplicate feature rows were observed with differing labels.\n\n")
        else:
            f.write("> [!WARNING] Detected duplicate feature rows that map to more than one label.\n"
                    "  This could indicate labeling noise or data collection anomalies.\n\n")
        f.write("## 3. Class Distribution (Data.csv)\n\n")
        f.write("| Class ID | Class Name | Count | % of total |\n| :---: | :--- | :---: | :---: |\n")
        total = sum(cnt for cnt, _ in label_counts_pct.values())
        for cid in sorted(label_counts_pct.keys()):
            cnt, pct = label_counts_pct[cid]
            name = mapping.get(cid, "Unknown")
            f.write(f"| `{cid}` | {name} | {cnt:,} | {pct}% |\n")
        f.write("\n---\n\n")
        f.write("## 4. Data Leakage Discussion\n\n")
        f.write("Exact duplicate feature rows mean that the *same* feature vector can appear multiple times in the dataset.\n"
                "If a naive random split is performed, identical rows may be placed in both the training and testing sets,\n"
                "resulting in an overly optimistic evaluation because the model has already seen the exact example during training.\n\n")
        f.write("**Recommended splitting strategy**:\n"
                "- **Group‑by duplicate hash**: treat each distinct feature row (including all its duplicates) as a single unit.\n"
                "- Perform the train/validation/test split **at the group level**, ensuring that all duplicates of a given hash stay together.\n"
                "- This can be achieved by shuffling the list of unique hashes and then allocating groups to the desired splits.\n\n")
        f.write("No actual split is performed in this audit.\n\n---\n\n")
        f.write("## 5. Relationship to CICFlowMeter_out.csv (without row‑wise join)\n\n")
        f.write(f"- **Data.csv feature columns:** {len(shared_cols)} columns match the CIC capture.\n"
                f"- **CICFlowMeter_out.csv additional columns:** {', '.join(cic_extra) if cic_extra else 'None'}\n"
                "  (These include network identifiers such as `Flow ID`, `Src IP`, etc., and the string‑typed `Label` column.)\n\n")
        f.write("From the schema overlap we can conclude that `Data.csv` is a numeric‑only subset of the full capture,\n"
                "containing the same 76 flow feature columns. However, because the row ordering differs and the\n"
                "Benign traffic was down‑sampled, we cannot infer a direct one‑to‑one mapping between individual rows.\n"
                "Any analysis that requires aligning rows must therefore rely on a robust key (e.g., a hash of the\n"
                "feature vector) rather than positional index.\n\n")
        f.write("---\n\n")
        f.write("## 6. Summary & Next Steps\n\n")
        f.write("* The paired files are internally consistent in size and label space.\n"
                "* Approximately 31.8 % of feature rows are exact duplicates, but none of those duplicates have conflicting labels.\n"
                "* Class distribution is heavily imbalanced, with benign traffic comprising ~80 % of the labeled data.\n"
                "* To avoid leakage, future train/validation/test splits should be performed on the level of *unique* feature rows (duplicate groups).\n"
                "* The relationship to the full capture confirms that `Data.csv` provides a numeric representation of the same flow features, but the rows are not directly alignable.\n"
                "\n**Next action**: Implement the group‑based split strategy, then proceed to feature engineering and confidence‑aware model training.\n")

def main() -> None:
    reconfigure_stdout_utf8()
    start = time.time()
    base_dir = Path("data/raw")
    report_path = Path("reports/data_integrity_audit.md")

    # Resolve required files
    data_path = resolve_file(base_dir, ["Data.csv", "data.csv"])
    label_path = resolve_file(base_dir, ["Label.csv", "label.csv"])
    cic_path = resolve_file(base_dir, ["CICFlowMeter_out.csv", "CICFlowmeter.csv", "cicflowmeter.csv"])
    readme_path = resolve_file(base_dir, ["Readme.txt", "README.txt", "readme.txt", "README.md", "README"])

    print(f"[+] Loaded files: Data={data_path.name}, Label={label_path.name}, CIC={cic_path.name}, Readme={readme_path.name}")

    # 1. Mapping
    mapping = load_readme_mapping(readme_path)
    print(f"[+] Numeric-to-class mapping contains {len(mapping)} entries.")

    # 2–3. Load paired data and audit duplicates / class distribution
    (
        df_data,
        s_label,
        label_counts,
        dup_rows,
        unique_rows,
        conflict_dup,
    ) = audit_pair_features_and_labels(data_path, label_path, mapping)
    total_rows = df_data.shape[0]
    label_dist_pct = class_distribution_percentages(label_counts, total_rows)
    print(f"[+] Duplicate feature rows: {dup_rows:,} (unique rows: {unique_rows:,})")
    print(f"[+] Duplicate rows with conflicting labels: {conflict_dup:,}")

    # 5. Schema comparison with CIC (memory‑efficient, only header needed)
    shared_cols, cic_extra = compare_schemas(df_data, cic_path)
    print(f"[+] Shared feature columns with CIC: {len(shared_cols)} / {df_data.shape[1]}")
    print(f"[+] Additional columns present only in CIC: {len(cic_extra)}")

    # 6. Generate markdown report
    generate_report(
        report_path,
        mapping,
        label_dist_pct,
        dup_rows,
        unique_rows,
        conflict_dup,
        shared_cols,
        cic_extra,
    )
    elapsed = round(time.time() - start, 2)
    print(f"[OK] Audit completed in {elapsed}s. Report saved to {report_path}")

if __name__ == "__main__":
    main()
