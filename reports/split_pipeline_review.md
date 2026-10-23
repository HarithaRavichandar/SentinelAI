# SentinelAI – Phase 1 Data Split Pipeline Review & Validation Report

> **Status:** Phase 1 Independently Validated  
> **Date:** October 20, 2026  
> **Repository:** `h:/SentinelAI`  
> **Target:** Final independent empirical verification of Phase 1 data pipeline prior to starting Phase 2.

---

## 1. Executive Summary

A comprehensive, independent audit and empirical validation of Phase 1 (Data Exploration, Integrity Auditing, and Leak-Resistant Partitioning) was performed. 

Key validation findings:
1. **Dataset Dimensions & Integrity:** Exactly **447,915** records with **76** numerical features (`Data.csv`) match `Label.csv` 1-to-1 with no missing values or infinite entries.
2. **True Unique Feature Vectors:** Exactly **305,602** unique feature vectors exist across the 76 features. The earlier figure of **283,720** reported in `reports/data_integrity_audit.md` has been identified and proven to be the count of **singleton rows** (records appearing strictly once), which was incorrectly labeled as "unique feature rows" due to subtracting all duplicate-group rows ($447,915 - 164,195 = 283,720$).
3. **Duplicate Group & Excess Row Accounting:** There are **21,882** multi-row duplicate groups containing a total of **164,195** rows (`duplicated(keep=False)`). Subtracting the 21,882 unique representatives leaves **142,313** redundant excess rows (`duplicated(keep='first')`, exactly matching the $31.77\%$ reported in `reports/data_profile.md`).
4. **Label Conflicts:** Exactly **497** duplicate feature groups share identical 76-dimensional feature vectors but have conflicting class labels, spanning **8,909** total rows.
5. **Partition Quality & Leakage Prevention:** The generated train, validation, and test masks (`train_mask.npy`, `val_mask.npy`, `test_mask.npy`) were verified to be strictly Boolean, completely partition the 447,915 records without omission or overlap (70.00% / 15.00% / 15.00%), and maintain **100% duplicate-group isolation** (0 groups split across partitions).
6. **Reproducibility:** Seed 42 is fully deterministic and produces identical masks.

---

## 2. Independent Empirical Recomputation vs. Prior Reports

All values were independently calculated directly from raw source files (`data/raw/Data.csv`, `data/raw/Label.csv`, `data/raw/Readme.txt`) using vectorized and collision-verified hashing:

| Metric | Verified Value | `reports/data_profile.md` | `reports/data_integrity_audit.md` | `reports/split_report.md` | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Total Rows** | **447,915** | 447,915 | 447,915 | 447,915 | **Consistent** |
| **Unique Feature Vectors** | **305,602** | Implicit ($447,915 - 142,313$) | 283,720 *(misnomer)* | 305,602 | **Resolved** |
| **Singleton Rows (Count = 1)** | **283,720** | Not reported | 283,720 *(labeled as unique)* | Not explicitly separated | **Resolved** |
| **Multi-Row Groups (Count > 1)** | **21,882** | Not reported | Not reported | $305,602 - 283,720$ | **Verified** |
| **Rows in Repeated Groups** | **164,195** | Not reported | 164,195 | 164,195 | **Consistent** |
| **Duplicate Excess Rows** | **142,313** | 142,313 (31.77%) | Not reported | 142,313 | **Consistent** |
| **Conflicting-Label Groups** | **497** | Not reported | Mentioned in sec 2, denied in sec 6 | 497 | **Resolved** |
| **Rows in Conflicting Groups** | **8,909** | Not reported | 8,909 | 8,909 | **Consistent** |

### Mathematical Reconciliation of Divergences

1. **The 283,720 vs. 305,602 Discrepancy:**
   - In `scripts/audit_dataset.py`, the code executed:
     ```python
     dup_mask = pd.Series(row_hashes).duplicated(keep=False)
     dup_rows = dup_mask.sum()          # 164,195
     unique_rows = df.shape[0] - dup_rows  # 447,915 - 164,195 = 283,720
     ```
   - Subtracting all rows belonging to duplicate groups (`keep=False`) strips away *all* occurrences of repeated vectors, leaving only the rows that appear strictly once (singletons).
   - Adding the 21,882 multi-row group representatives back to the 283,720 singletons gives the true unique count:
     $$\text{Unique Groups} = 283,720 + 21,882 = \mathbf{305,602}$$
2. **The 142,313 vs. 164,195 Relationship:**
   - 164,195 is the count of *all* rows in non-unique groups (`keep=False`).
   - 142,313 is the count of *excess* duplicate copies beyond the first (`keep='first'`), which equals $164,195 - 21,882 = 142,313$.
   - This also satisfies: $447,915 - 142,313 = 305,602$.
3. **The Conflicting-Label Contradiction in Audit Report:**
   - `reports/data_integrity_audit.md` correctly identified 8,909 conflicting rows in Section 2, but Section 6 incorrectly noted in a summary bullet that "none of those duplicates have conflicting labels". Our empirical verification confirms Section 2: there are **497 conflicting groups affecting 8,909 rows**.

---

## 3. Mask Validation and Isolation Verification

The generated partition files in `data/processed/` were directly inspected and validated:
- `data/processed/train_mask.npy`
- `data/processed/val_mask.npy`
- `data/processed/test_mask.npy`

### A. Dimensionality and Data Type
- `train_mask`: shape `(447915,)`, dtype `bool`
- `val_mask`: shape `(447915,)`, dtype `bool`
- `test_mask`: shape `(447915,)`, dtype `bool`

### B. Partition Disjointness and Completeness
- **Train ∩ Val overlap:** `0` rows
- **Train ∩ Test overlap:** `0` rows
- **Val ∩ Test overlap:** `0` rows
- **Total assigned rows:** `447,915` ($100.0\%$)
- **Unassigned rows:** `0` ($0.0\%$)

### C. Split Proportions
- **Training Set:** `313,540` rows (**70.00%**)
- **Validation Set:** `67,187` rows (**15.00%**)
- **Test Set:** `67,188` rows (**15.00%**)

### D. Leak-Resistant Group Isolation
- Every exact feature group was mapped to its assigned split partition.
- **Groups split across partitions:** **0**
- Complete isolation confirmed: no identical feature vectors exist in more than one partition.

### E. Reproducibility
- Independent execution with `seed=42` produced exact bit-for-bit matches against `train_mask.npy`, `val_mask.npy`, and `test_mask.npy`.

---

## 4. Command Execution Log

### 1. Dataset Preparation Command
```bash
python scripts/prepare_dataset.py
```
- **Exit Status:** `0` (Success)
- **Execution Duration:** ~1 minute 54 seconds
- **Output Artifacts:** `data/processed/train_mask.npy`, `data/processed/val_mask.npy`, `data/processed/test_mask.npy`, `reports/split_report.md`.

### 2. PyTest Test Suite Command
```bash
python -m pytest -v
```
- **Exit Status:** `0` (Success - all 4 tests passed)
- **Execution Duration:** `760.41s` (12 minutes 40 seconds)
- **Suite Target:** [tests/test_data_split.py](file:///h:/SentinelAI/tests/test_data_split.py)
  - `tests/test_data_split.py::test_masks_shape_and_dtype PASSED [ 25%]`
  - `tests/test_data_split.py::test_partitions_disjoint_and_complete PASSED [ 50%]`
  - `tests/test_data_split.py::test_group_integrity PASSED [ 75%]`
  - `tests/test_data_split.py::test_reproducibility PASSED [100%]`
- **Full Console Output:**
```text
============================= test session starts =============================
platform win32 -- Python 3.11.7, pytest-8.1.1, pluggy-1.6.0 -- C:\Users\harit\anaconda3\python.exe
cachedir: .pytest_cache
rootdir: H:\SentinelAI
plugins: anyio-4.12.1
collecting ... collected 4 items

tests/test_data_split.py::test_masks_shape_and_dtype PASSED              [ 25%]
tests/test_data_split.py::test_partitions_disjoint_and_complete PASSED   [ 50%]
tests/test_data_split.py::test_group_integrity PASSED                    [ 75%]
tests/test_data_split.py::test_reproducibility PASSED                    [100%]

======================== 4 passed in 760.41s (0:12:40) ========================
```

---

## 5. Unresolved Limitations & Recommendations for Phase 2

1. **Conflicting-Label Groups (8,909 rows / 497 groups):**
   - Currently, these rows remain in the dataset. Because duplicate groups are kept intact, conflicting rows stay within a single partition, preventing cross-split leakage. However, training on identical feature vectors with contradictory labels introduces label noise.
   - *Phase 2 Recommendation:* Apply a label-resolution strategy (e.g. majority voting per group, assigning an "uncertain / ambiguous" label, or filtering unresolvable ties during training while retaining test fidelity).
2. **Extreme Class Imbalance:**
   - Class 0 (Benign) represents 80.00% of records, while attack classes such as Worms (Class 9, 246 rows / 0.055%) and Analysis (Class 1, 385 rows / 0.086%) have very few samples.
   - *Phase 2 Recommendation:* Implement class-weighted cross-entropy / focal loss and evaluate using stratified macro PR-AUC and balanced F1 scores.
3. **Pipeline Scalability Bottleneck:**
   - In `src/sentinelai/data/split.py`, `train_mask[group_ids == gid] = True` runs inside an iterative Python loop over 305,602 groups. While functional on this dataset (~1m 50s runtime), vectorizing group assignment with `numpy` indexing or `.map()` would reduce execution time from ~110 seconds to under 0.1 seconds.

---

## 6. Final Verdict

**Phase 1 is VALIDATED.** All raw dataset properties, duplicate groupings, conflict distributions, and leak-resistant split masks are verified empirically. The project is ready to advance to Phase 2 (Feature Engineering & Preprocessing).
