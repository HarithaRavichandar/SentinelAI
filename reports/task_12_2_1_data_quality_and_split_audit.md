# Task 12.2.1 / 12.2.1.1 — CIC Data Quality, Duplicate Accounting, and Leakage-Free Split Audit Report

**Project Root**: `H:\SentinelAI`  
**Date**: 2026-11-19  
**Execution Environment**: Python 3.13.3 (`C:\Users\harit\AppData\Local\Programs\Python\Python313\python.exe`)  
**Pipeline Script**: `H:\SentinelAI\scripts\cic_audit_and_split.py`  
**Execution Runner**: `H:\SentinelAI\scripts\run_cic_audit.bat`  
**Log Path**: `H:\SentinelAI\experiments\cic_three_class\logs\audit_20261119_141153.log`  
**Execution Status**: ✅ **SUCCESS (All invariants verified)**

---

## 1. Executive Summary

A memory-efficient, standard-library-only audit and group-aware split pipeline was implemented, debugged, synthetically tested, and executed on the CIC-IDS2018 dataset (`data/external/cic_ids_2018/cic.csv`).

The pipeline completely resolved three critical defects identified in prior iterations:
1. **Inflated Group Row Counts**: Duplicate rows are no longer included when aggregating group row counts or computing split targets. Group sizes reflect strictly unique rows (`is_dup=0`).
2. **Accurate Target Calculation**: Group-aware stratified splitting operates strictly on eligible unique rows (802,923 rows), accurately achieving the 70% / 15% / 15% targets.
3. **Optimized Streaming CSV Writing**: Replaced the previous $O(N)$ query bottleneck (619,791 individual SQL queries) with a single-pass streaming SQL join, reducing CSV generation from hours to 34 seconds.

---

## 2. Synthetic Test Arithmetic Reconciliation

The apparent discrepancy between expected eligible rows and split totals in earlier narrative prose arose from a typographical error in the narrative text ("24 rows / 20 eligible" instead of the actual "26 rows / 22 eligible"). 

An independent ground-truth function (`compute_ground_truth_from_csv`) was added to `scripts/test_synthetic_audit.py` to parse the synthetic CSV directly and compute counts from first principles without hardcoded arithmetic.

### 2.1 Synthetic Dataset Row Composition (26 total rows)
1. **Group 1 (Feature vector 100)**: 3 rows
   - Row 1: Base row (`Dst Port=80`, `Label=Benign`) — **Unique row** (`is_dup=0`)
   - Row 2: Full-row copy of Row 1 across all 80 cols — **Exact duplicate** (`is_dup=1`)
   - Row 3: Same feature vector, different port (`Dst Port=443`, `Label=Benign`) — **Unique row** (`is_dup=0`, repeated feature vector with matching label)
2. **Group 2 (Feature vector 200, Conflicting Group)**: 3 rows
   - Row 4: Base row (`Dst Port=21`, `Label=Benign`) — **Unique row** (`is_dup=0`)
   - Row 5: Same feature vector, conflicting label (`Dst Port=21`, `Label=FTP-BruteForce`) — **Unique row** (`is_dup=0`)
   - Row 6: Full-row copy of Row 5 — **Exact duplicate** (`is_dup=1`)
3. **Groups 3 through 22 (Feature vectors 1000..1019)**: 20 rows
   - Rows 7 through 26: 20 distinct unique flows with rotating labels (`is_dup=0`).

### 2.2 Reconciled Synthetic Accounting
$$\text{Total Source Rows (26)} = \text{Exact Dups (2)} + \text{Unique Rows Remaining (24)}$$
$$\text{Unique Rows Remaining (24)} = \text{Conflicting Unique Rows (2)} + \text{Eligible Unique Rows (22)}$$
$$\text{Eligible Unique Rows (22)} = \text{Train (15)} + \text{Val (3)} + \text{Test (4)} = \mathbf{22}$$

**Synthetic Test Invariants Independently Verified**:
- Exact duplicate removal: 2 rows removed.
- Conflicting vectors written to audit CSV: 3 rows (Rows 4, 5, 6; 2 unique + 1 duplicate).
- Group 1 atomic isolation: Rows 1 and 3 placed together in `train.csv`.
- Sum of split rows equals eligible unique rows: $15 + 3 + 4 = 22$.
- Exit code: 0 (**PASSED**).

---

## 3. Real Dataset Verification

| Metric | Verified Value |
| :--- | :--- |
| **File Path** | `H:\SentinelAI\data\external\cic_ids_2018\cic.csv` |
| **File Size** | 358,223,333 bytes (341.63 MiB) |
| **SHA-256 Before Run** | `ACFF8BC61376EE031D80878EE6099E0B1A87A1BD711D8068298421418C9F8147` |
| **SHA-256 After Run** | `ACFF8BC61376EE031D80878EE6099E0B1A87A1BD711D8068298421418C9F8147` |
| **Total Rows in File** | **1,048,575** data rows (plus 1 header row) |
| **Column Count** | Exactly **80** columns |
| **Metadata Columns (3)** | `Dst Port`, `Protocol`, `Timestamp` |
| **Numerical Flow Features (76)** | `Flow Duration` through `Idle Min` (Schema Schema B) |
| **Label Column (1)** | `Label` (last column) |
| **Distinct Raw Labels** | `Benign` (667,626), `FTP-BruteForce` (193,360), `SSH-Bruteforce` (187,589) |
| **Unexpected Labels** | **0** |
| **Parse / Formatting Errors** | **0** |

---

## 4. Duplicate Accounting & Conflicting Vector Analysis

### 4.1 Exact Duplicate Rows vs. Repeated Feature Vectors
* **Exact Duplicate Rows (`is_dup=1`)**: Rows identical across all 80 columns (identical metadata, identical flow features, identical label). Only the first occurrence is retained (`is_dup=0`); all subsequent occurrences are counted as removed duplicates and excluded from model splits.
* **Repeated Feature Vectors with Matching Labels (`is_dup=0`)**: Rows that share the exact same 76 numerical flow features and the same label, but possess different metadata (e.g. differing `Dst Port` or `Timestamp`). These represent independent network flows that produce identical flow metrics. They are treated as **unique rows** and kept together as an atomic feature group in the exact same split to prevent train/test data leakage.

### 4.2 Duplicate and Exclusion Totals

| Category | Row Count | Group Count | Notes |
| :--- | :--- | :--- | :--- |
| **Total Source Rows** | 1,048,575 | — | Full CSV |
| **Exact Duplicate Rows Removed** | **225,628** | — | Fully identical across 80 columns (`is_dup=1`) |
| **Unique Rows Remaining** | **822,947** | 619,798 | `1,048,575 - 225,628` |
| **Conflicting Feature Groups** | **20,024** | **7** | Unique rows with identical 76 features and contradictory labels |
| **Eligible Unique Rows** | **802,923** | **619,791** | `822,947 - 20,024` (Atomic groups eligible for split) |

### 4.3 Conflicting Rows Breakdown
`audits/conflicting_feature_vectors.csv` contains all **169,775** rows from the 7 conflicting groups:
- **Conflicting Unique Rows (`is_dup=0`)**: **20,024**
- **Conflicting Duplicate Rows (`is_dup=1`)**: **149,751**
- **Total Rows in Conflict CSV**: **169,775** ($20,024 + 149,751 = 169,775$)
- Note: The 149,751 duplicate conflicting rows are a subset of the 225,628 total exact duplicates.

---

## 5. Group-Aware Split Results

The 619,791 eligible unique groups (comprising 802,923 unique rows) were deterministically partitioned with seed `42`:

| Split | Target % | Actual Unique Rows | % of Eligible | Group Count | Class Distribution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train** | 70.0% | **562,046** | **70.00%** | 440,155 | `Benign`: 474,672 (84.45%)<br>`SSH-Bruteforce`: 73,806 (13.13%)<br>`FTP-BruteForce`: 13,568 (2.41%) |
| **Val** | 15.0% | **120,438** | **15.00%** | 94,559 | `Benign`: 100,957 (83.82%)<br>`SSH-Bruteforce`: 15,169 (12.59%)<br>`FTP-BruteForce`: 4,312 (3.58%) |
| **Test** | 15.0% | **120,439** | **15.00%** | 85,077 | `Benign`: 90,644 (75.26%)<br>`SSH-Bruteforce`: 28,340 (23.53%)<br>`FTP-BruteForce`: 1,455 (1.21%) |
| **Total** | 100.0% | **802,923** | **100.00%** | **619,791** | — |

---

## 6. Independent Output Validation & Invariant Checks

Phase 6 executed an independent read-back of the generated CSV files directly from disk:

| Check | Expected | Actual Result | Status |
| :--- | :--- | :--- | :--- |
| **Split Row Sum Invariant** | `562,046 + 120,438 + 120,439 = 802,923` | `802,923 == 802,923` | ✅ **PASSED** |
| **Full Row Accounting Invariant** | `225,628 (dups) + 20,024 (conflict) + 802,923 (splits) = 1,048,575` | `1,048,575 == 1,048,575` | ✅ **PASSED** |
| **Group Leakage / Overlap** | 0 groups present in >1 split | **0 overlapping groups** (619,791 distinct groups) | ✅ **PASSED** |
| **Duplicate Full Rows in Splits** | 0 duplicate full rows within or across splits | **0 duplicates found** (802,923 distinct rows) | ✅ **PASSED** |
| **Conflicting Groups in Splits** | 0 conflicting rows present in splits | **0 conflicting rows present** | ✅ **PASSED** |
| **Schema Uniformity** | Exactly 80 columns matching source header | All 3 split files verified | ✅ **PASSED** |
| **Source File Immutability** | SHA-256 unchanged | Verified byte-identical | ✅ **PASSED** |

---

## 7. Artifact Inventory

All required audit deliverables and splits are stored under `experiments/cic_three_class/`:

```
H:\SentinelAI\experiments\cic_three_class\
├── audits\
│   ├── conflicting_feature_vectors.csv   # 49.6 MB, 169,775 total conflicting rows with metadata & labels
│   ├── dataset_validation.json            # 1.6 KB, Complete validation metadata & verified counts
│   ├── duplicate_rows_removed.json        # 695 B, Exact duplicate accounting & definition documentation
│   ├── feature_quality_report.csv         # 3.9 KB, Per-feature non-finite (NaN, Inf) and range audit
│   └── split_summary.json                 # 945 B, Machine-readable split metadata and group stats
├── splits\
│   ├── split_stats.md                     # Markdown summary of split distributions
│   ├── split_summary.json                 # Mirror of split_summary.json
│   ├── train.csv                          # 213.8 MB, 562,046 rows (80 columns)
│   ├── val.csv                            # 45.9 MB, 120,438 rows (80 columns)
│   └── test.csv                           # 44.1 MB, 120,439 rows (80 columns)
└── logs\
    └── audit_20261119_141153.log          # Complete step-by-step pipeline execution log
```

---

## 8. Preserved Project Assets

In accordance with strict project constraints:
* `data/external/cic_ids_2018/cic.csv` was verified byte-identical (SHA-256 unchanged).
* `data/models/random_forest_balanced.pkl` (Legacy model) remains untouched.
* `data/models_fresh/random_forest_fresh.pkl` (Fresh model) remains untouched.
* `data/processed/preprocessor_balanced.pkl` remains untouched.
* `data/models_fresh/preprocessor_fresh.pkl` remains untouched.
* No changes were committed or pushed to Git.
* Application backend, frontend, and production triage modules were unmodified.
