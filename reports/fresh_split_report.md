# SentinelAI – Fresh Data Split Report (Seed 101)

> **Document Status**: Final Report for Step 1 of Fresh Evaluation Pipeline  
> **Generated At**: 2026-10-29T21:12:25Z  
> **Random Seed**: `101` | **Target Ratios**: 70% Train, 15% Val, 15% Test  

---

## 1. Executive Summary & Purpose

This report documents the preparation of a fresh, group-aware data split for SentinelAI. The split isolates duplicate network flows so that no exact feature duplicate spans multiple partitions. Critically, **conflicting duplicate groups** (flows with identical 76 numeric features but conflicting ground-truth labels) have been quarantined into a dedicated partition, establishing a mathematically sound, clean benchmark for primary model evaluation.

> [!IMPORTANT]
> All legacy models (`data/models/`), legacy masks (`data/processed/`), and production policies remain untouched. Fresh artifacts reside exclusively in `data/processed_fresh/`.

---

## 2. Dataset Fingerprint & Integrity Hashes

- **Total Rows**: 447,915
- **Total Features**: 76
- `Data.csv` SHA-256: `60d55f4f8f1e72bdfa2e0c1c74c03ac301bd880af321fdad1ba453950a7aa16a`
- `Label.csv` SHA-256: `5b2fcf31dc2d03ac6a07f8791858e55d86306f05442c3a4528bcc67301956a56`
- `Readme.txt` SHA-256: `5850f5b8e82f5a2980030f10819dd25b8ddff9c66f753ae27e818becbeb0df31`

---

## 3. Duplicate Groups & Conflicting Labels Analysis

- **Total Rows**: 447,915
- **Unique Exact Feature Groups**: 305,602
- **Singleton Groups (1 row)**: 283,720
- **Multi-Row Groups (>1 row)**: 21,882 (164,195 flows, 36.66% of dataset)
- **Conflicting Groups Quarantined**: **497 groups** (8,909 rows, 1.99% of dataset)
- **Clean Population for Primary Split**: **305,105 groups** (439,006 rows, 98.01% of dataset)

### 3.1 Class-Level Impact of Conflicting Duplicate Exclusion

| Class ID | Class Name | Total Rows | Excluded Rows | % Excluded | Retained Clean Rows |
| :---: | :--- | :---: | :---: | :---: | :---: |
| `0` | Benign | 358,332 | 712 | 0.2% | 357,620 |
| `1` | Analysis | 385 | 0 | 0.0% | 385 |
| `2` | Backdoor | 452 | 0 | 0.0% | 452 |
| `3` | DoS | 4,467 | 139 | 3.11% | 4,328 |
| `4` | Exploits | 30,951 | 89 | 0.29% | 30,862 |
| `5` | Fuzzers | 29,613 | 3,264 | 11.02% | 26,349 |
| `6` | Generic | 4,632 | 173 | 3.73% | 4,459 |
| `7` | Reconnaissance | 16,735 | 4,200 | 25.1% | 12,535 |
| `8` | Shellcode | 2,102 | 326 | 15.51% | 1,776 |
| `9` | Worms | 246 | 6 | 2.44% | 240 |

> [!WARNING]
> **Population Restriction Limitation**: Excluding conflicting groups removes 25.10% of Reconnaissance flows, 15.51% of Shellcode flows, and 11.02% of Fuzzers flows due to label contradictions in the raw UNSW-NB15 benchmark. The primary evaluation measures model performance strictly on non-contradictory ground truth. The 8,909 quarantined rows will be evaluated separately in a secondary analysis to measure triage uncertainty handling.

---

## 4. Fresh Partition Sizes & Proportions

| Partition | Rows | % of Total Dataset | % of Clean Subset | Distinct Groups |
| :--- | :---: | :---: | :---: | :---: |
| **Train Fresh** | 307,304 | 68.61% | 70.00% | 214,078 |
| **Validation Fresh** | 65,850 | 14.70% | 15.00% | 45,273 |
| **Test Fresh (Held-out)** | 65,852 | 14.70% | 15.00% | 45,754 |
| **Conflict Set (Quarantined)** | 8,909 | 1.99% | N/A | 497 |
| **Total** | **447,915** | **100.00%** | **100.00%** | **305,602** |

---

## 5. Class Distribution per Fresh Partition

| Class ID | Class Name | Train Fresh | Val Fresh | Test Fresh | Conflict Set |
| :---: | :--- | :---: | :---: | :---: | :---: |
| `0` | Benign | 250,140 | 53,862 | 53,618 | 712 |
| `1` | Analysis | 271 | 57 | 57 | 0 |
| `2` | Backdoor | 325 | 66 | 61 | 0 |
| `3` | DoS | 3,065 | 596 | 667 | 139 |
| `4` | Exploits | 21,671 | 4,585 | 4,606 | 89 |
| `5` | Fuzzers | 18,515 | 3,868 | 3,966 | 3,264 |
| `6` | Generic | 3,123 | 653 | 683 | 173 |
| `7` | Reconnaissance | 8,795 | 1,846 | 1,894 | 4,200 |
| `8` | Shellcode | 1,227 | 284 | 265 | 326 |
| `9` | Worms | 172 | 33 | 35 | 6 |

All 10 classes are represented across all three clean partitions.

---

## 6. Cross-Split Overlap Matrix (Legacy vs Fresh)

### 6.1 Row-Level Overlap Matrix

| Legacy Split (`seed=42`) | Train Fresh | Val Fresh | Test Fresh | Conflict Set | Total Legacy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Legacy Train** | 216,485 | 45,551 | 45,465 | 6,039 | 313,540 |
| **Legacy Val** | 45,419 | 10,077 | 10,191 | 1,500 | 67,187 |
| **Legacy Test** | 45,400 | 10,222 | 10,196 | 1,370 | 67,188 |

### 6.2 Group-Level Overlap Audit of `test_fresh`

- Total distinct groups in `test_fresh`: **45,754 groups**
- `test_fresh` groups that appeared in Legacy Training: **31,956 groups** (69.84%)
- `test_fresh` groups that appeared in Legacy Validation: **6,866 groups** (15.01%)
- `test_fresh` groups that appeared in Legacy Test: **6,932 groups** (15.15%)

> [!CAUTION]
> **Cross-Split Exposure Disclosure**: As expected in any closed dataset re-splitting, **69.84%** of the feature groups assigned to `test_fresh` were part of the training set used to build the *legacy* Random Forest model (`data/models/random_forest_balanced.pkl`). Therefore, `test_fresh` is **NOT** an independent out-of-distribution dataset. However, relative to the **fresh model** (`random_forest_fresh.pkl`), `test_fresh` has strictly **zero group overlap** with `train_fresh` and `val_fresh`. Evaluating on `test_fresh` guarantees clean, unblinded generalization without circular parameter calibration.

---

## 7. Verification & Leakage Assertion Checklist

- [x] **Mask Mutual Exclusivity**: Every row belongs to exactly one mask (`counts_per_row == 1`).
- [x] **Exhaustive Population Coverage**: All 447,915 rows accounted for across the 4 masks.
- [x] **Strict Group Isolation**: Zero group overlap across `train_fresh`, `val_fresh`, `test_fresh`, and `conflict_mask_fresh`.
- [x] **Class Coverage**: Every class has non-zero representation across train, val, and test.
- [x] **Legacy Asset Protection**: Existing files in `data/processed/` and `data/models/` verified unchanged.
