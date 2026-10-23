# SentinelAI: Dataset Exploration and Validation Report (Phase 1)

> **Notice:** This profile is generated strictly from empirical analysis of the raw CSV files and metadata located in `data/raw/`. No transformations, row deletions, or synthetic labels have been applied. Provenance names (such as UNSW-NB15 or CIC-IDS2017) are not claimed without explicit official source metadata.

---

## 1. Executive Summary & File Inventory

| File Name | File Size | Shape (Rows, Columns) | Total Missing | Total Infs | Duplicate Rows |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Data.csv` | 187.16 MB | `(447915, 76)` | 0 | 0 | 142313 (31.77%) |
| `Label.csv` | 0.85 MB | `(447915, 1)` | 0 | 0 | 447905 |
| `CICFlowMeter_out.csv` | 1825.62 MB | `(3540241, 84)` | 0 | 0 | 59906 (1.69%) |

---

## 2. Row Compatibility & Overlap Analysis

### A. `Data.csv` vs `Label.csv` Compatibility
- **`Data.csv` Row Count:** 447,915
- **`Label.csv` Row Count:** 447,915
- **Compatible Row Counts:** `YES`
- **Assessment:** Both files have identical lengths (447,915 rows).

### B. Cross-File Relationship with `CICFlowMeter_out.csv`
- `CICFlowMeter_out.csv` contains **3,540,241 rows** and **84 columns**.
- It shares **76 statistical flow feature columns** with `Data.csv` in identical order.
- It additionally includes **7 network metadata columns**: `Flow ID, Src IP, Src Port, Dst IP, Dst Port, Protocol, Timestamp`.
- It includes a string-typed **`Label`** column as its 84th column.

### C. Row Alignment Verification & Divergence
- **Rows 0 to 33:** The first 34 rows of `Data.csv` and `Label.csv` perfectly match the features and mapped labels of `CICFlowMeter_out.csv`.
- **Divergence at Row 34:** At index 34, `CICFlowMeter_out.csv` continues with Benign records, whereas `Data.csv` and `Label.csv` jump to an attack flow (`Exploits` / Label 4).
- **Empirical Finding:** `Data.csv` and `Label.csv` represent a **subsampled version** of the full capture found in `CICFlowMeter_out.csv`. Specifically, the non-attack (Benign) traffic was subsampled by approximately 9.6x (from 3,450,658 down to 358,332), while **all 89,583 attack instances across all 9 attack categories are preserved exactly**.
> [!IMPORTANT]
> **Never align `CICFlowMeter_out.csv` and `Data.csv` naively by row index.** Because rows were dropped during benign subsampling without preserving original row IDs or index keys, positional row joins between `Data.csv` and `CICFlowMeter_out.csv` will produce severe data corruption.

---

## 3. Label Distributions and Mappings

### A. Numeric Label Mapping (`Readme.txt`)
| Numeric ID | Class Name |
| :---: | :--- |
| `0` | Benign |
| `1` | Analysis |
| `2` | Backdoor |
| `3` | DoS |
| `4` | Exploits |
| `5` | Fuzzers |
| `6` | Generic |
| `7` | Reconnaissance |
| `8` | Shellcode |
| `9` | Worms |

### B. Comparative Class Distribution

| Class ID | Attack Category | `Label.csv` Count | `Label.csv` Pct | `CICFlowMeter_out.csv` Count | `CICFlowMeter_out.csv` Pct | Preserved Ratio |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| `0` | **Benign** | 358,332 | 80.0% | 3,450,658 | 97.47% | 10.38% (Subsampled) |
| `1` | **Analysis** | 385 | 0.086% | 385 | 0.011% | 100.0% (Exact) |
| `2` | **Backdoor** | 452 | 0.101% | 452 | 0.013% | 100.0% (Exact) |
| `3` | **DoS** | 4,467 | 0.997% | 4,467 | 0.126% | 100.0% (Exact) |
| `4` | **Exploits** | 30,951 | 6.91% | 30,951 | 0.874% | 100.0% (Exact) |
| `5` | **Fuzzers** | 29,613 | 6.611% | 29,613 | 0.836% | 100.0% (Exact) |
| `6` | **Generic** | 4,632 | 1.034% | 4,632 | 0.131% | 100.0% (Exact) |
| `7` | **Reconnaissance** | 16,735 | 3.736% | 16,735 | 0.473% | 100.0% (Exact) |
| `8` | **Shellcode** | 2,102 | 0.469% | 2,102 | 0.059% | 100.0% (Exact) |
| `9` | **Worms** | 246 | 0.055% | 246 | 0.007% | 100.0% (Exact) |

---

## 4. Column Names, Whitespace, & Unexpected Formatting

### A. Whitespace and Duplicates
- **Leading / Trailing Whitespace:** None detected in any of the three CSVs.
- **Duplicate Column Names:** None detected in any of the three CSVs.

### B. Formatting Anomalies & Casing Inconsistencies
- **Special Characters:** Multiple columns include forward slashes (`/`), which can cause issues with certain downstream tools or SQL engines if unescaped:
  - `Flow Bytes/s`, `Flow Packets/s`, `Fwd Packets/s`, `Bwd Packets/s`, `Down/Up Ratio`
  - Bulk rate averages: `Fwd Bytes/Bulk Avg`, `Fwd Packet/Bulk Avg`, `Fwd Bulk Rate Avg`, `Bwd Bytes/Bulk Avg`, `Bwd Packet/Bulk Avg`, `Bwd Bulk Rate Avg`
- **Internal Spaces:** 75 of 76 columns in `Data.csv` contain spaces (e.g. `Flow Duration`, `Total Fwd Packet`).
- **Pluralization / Capitalization Inconsistencies:**
  - `Total Fwd Packet` (singular, Title Case) vs `Total Bwd packets` (plural, lowercase `p`).
  - `Subflow Fwd Packets` (plural) vs `Subflow Bwd Packets` (plural).
  - `FWD Init Win Bytes` (all caps `FWD`) vs `Bwd Init Win Bytes` (Title Case `Bwd`).

---

## 5. Data Types, Missing Values, and Anomalies

### `Data.csv`
- **Shape:** 447,915 rows x 76 columns
- **Data Types:** {'float64': 45, 'int64': 31}
- **Missing Values:** 0 (0.0%)
- **Infinite Values:** 0 (0.0%)
- **Duplicate Rows:** 142,313 (31.77% of the dataset)
> [!WARNING]
> Over 31.7% of rows in `Data.csv` (142,313 rows) are exact duplicates across all 76 features. This is common in network flow captures (e.g., repeated connection attempts, TCP port sweeps, or zero-payload keepalive flows). If not addressed properly during cross-validation, duplicate rows will leak between training and validation folds.

### `Label.csv`
- **Shape:** 447,915 rows x 1 column
- **Data Types:** {'int64': 1}
- **Missing Values:** 0 (0.0%)
- **Infinite Values:** 0 (0.0%)

### `CICFlowMeter_out.csv`
- **Shape:** 3,540,241 rows x 84 columns
- **Data Types:** {'float64': 45, 'int64': 34, 'object': 5}
- **Missing Values:** 0 (0.0%)
- **Infinite Values:** 0 (0.0%)
- **Duplicate Rows:** 59,906 (1.69% of the dataset)

---

## 6. Assumptions and Limitations

1. **Read-Only Inspection:** No rows were removed, cleaned, or modified in any raw file.
2. **Memory Constraints:** `CICFlowMeter_out.csv` is ~1.91 GB and contains over 3.54 million rows. It was processed via bounded chunk streaming to operate within host memory constraints.
3. **No Unverified Attribution:** While feature headers match CICFlowMeter outputs and attack categories (e.g. Fuzzers, Analysis, Backdoor) resemble modern network benchmark datasets, no definitive attribution to a specific public benchmark (such as UNSW-NB15 or CIC-IDS2017) is claimed without official benchmark metadata.
4. **No Naive Alignment:** While `Data.csv` and `Label.csv` share identical row counts and match class distributions, any cross-referencing against `CICFlowMeter_out.csv` cannot be done by row position due to benign traffic downsampling.
5. **High Imbalance:** Class 0 (Benign) represents 80.0% of `Data.csv` / `Label.csv` and 97.47% of `CICFlowMeter_out.csv`. Rare classes such as `Worms` (246 samples, 0.055%) and `Analysis` (385 samples, 0.086%) will require stratified sampling and specialized confidence calibration.

---
*Report generated automatically by `scripts/inspect_dataset.py`.*
