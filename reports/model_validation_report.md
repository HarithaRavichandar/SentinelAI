# SentinelAI - Random Forest Model Validation Report

**Generated:** 2026-10-29 06:17:30 UTC

## 1. Executive Summary

- **Model Artifact:** `random_forest_balanced.pkl`
- **Preprocessor Artifact:** `preprocessor_balanced.pkl`
- **Evaluation Partition:** `TEST` (67,188 rows, 15.00% of total 447,915 records)
- **Overall Accuracy:** `0.9141` (91.41%)
- **Balanced Accuracy:** `0.5375` (53.75%)
- **Macro-F1 Score:** `0.5424`
- **Weighted-F1 Score:** `0.9153`
- **Total Inference Latency:** `0.7744s` (~`11.53 μs` per flow)

---

## 2. Pipeline Alignment Verification

| Check | Expected | Actual | Status |
| :--- | :---: | :---: | :---: |
| Feature Count | 76 | 76 | PASS |
| Feature Order Alignment | Exact Match | Matched | PASS |
| Scaler Compatibility | Fitted (76 features) | Compatible | PASS |
| Class ID Mapping | 10 classes (0-9) | 10 classes | PASS |
| Train/Test Isolation | Zero overlap | Disjoint confirmed | PASS |

---

## 3. Class Coverage & Representation

All **10 classes** (`Benign, Analysis, Backdoor, DoS, Exploits, Fuzzers, Generic, Reconnaissance, Shellcode, Worms`) are represented in the evaluation partition.

## 4. Per-Class Classification Performance

| Class ID | Class Name | Precision | Recall | F1-Score | Support | % of Split |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| `0` | **Benign** | 0.9916 | 0.9813 | 0.9864 | 53,562 | 79.720% |
| `1` | **Analysis** | 0.3542 | 0.2833 | 0.3148 | 60 | 0.089% |
| `2` | **Backdoor** | 0.8478 | 0.5342 | 0.6555 | 73 | 0.109% |
| `3` | **DoS** | 0.4024 | 0.2865 | 0.3347 | 691 | 1.028% |
| `4` | **Exploits** | 0.7480 | 0.7860 | 0.7665 | 4,612 | 6.864% |
| `5` | **Fuzzers** | 0.6216 | 0.7397 | 0.6755 | 4,564 | 6.793% |
| `6` | **Generic** | 0.5239 | 0.7293 | 0.6098 | 676 | 1.006% |
| `7` | **Reconnaissance** | 0.6508 | 0.3930 | 0.4901 | 2,613 | 3.889% |
| `8` | **Shellcode** | 0.0899 | 0.2273 | 0.1288 | 308 | 0.458% |
| `9` | **Worms** | 0.5217 | 0.4138 | 0.4615 | 29 | 0.043% |

---

## 5. Confusion Matrix (Rows = Ground Truth, Columns = Predicted)

| Ground Truth \ Predicted | **Benign** (0) | **Analysis** (1) | **Backdoor** (2) | **DoS** (3) | **Exploits** (4) | **Fuzzers** (5) | **Generic** (6) | **Recon** (7) | **Shellcode** (8) | **Worms** (9) | **Total** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Benign** (`0`) | 52,561 | 18 | 1 | 37 | 153 | 648 | 58 | 69 | 17 | 0 | **53,562** |
| **Analysis** (`1`) | 16 | 17 | 0 | 5 | 22 | 0 | 0 | 0 | 0 | 0 | **60** |
| **Backdoor** (`2`) | 0 | 0 | 39 | 1 | 15 | 9 | 0 | 7 | 1 | 1 | **73** |
| **DoS** (`3`) | 18 | 1 | 0 | 198 | 291 | 123 | 14 | 38 | 8 | 0 | **691** |
| **Exploits** (`4`) | 86 | 12 | 4 | 33 | 3,625 | 594 | 29 | 213 | 12 | 4 | **4,612** |
| **Fuzzers** (`5`) | 233 | 0 | 1 | 61 | 328 | 3,376 | 334 | 190 | 37 | 4 | **4,564** |
| **Generic** (`6`) | 11 | 0 | 0 | 6 | 70 | 71 | 493 | 16 | 7 | 2 | **676** |
| **Recon** (`7`) | 64 | 0 | 0 | 148 | 286 | 453 | 8 | 1,027 | 627 | 0 | **2,613** |
| **Shellcode** (`8`) | 13 | 0 | 1 | 3 | 48 | 150 | 5 | 18 | 70 | 0 | **308** |
| **Worms** (`9`) | 2 | 0 | 0 | 0 | 8 | 7 | 0 | 0 | 0 | 12 | **29** |

---

## 6. Evaluation Methodology & Limitations

### Methodology
- **Artifact Integrity:** Evaluates the serialized `RandomForestClassifier` (`data/models/random_forest_balanced.pkl`) and `StandardScaler` (`data/processed/preprocessor_balanced.pkl`) strictly in inference mode without retraining.
- **Partitioning:** Sourced from the official `test_mask.npy` partition created during Phase 1. The split was constructed with **duplicate-group isolation** (zero exact feature duplicates shared across train, val, and test).
- **Feature Alignment:** Features are projected in the exact order recorded in `preprocessor['columns']` and scaled using the preprocessor's training-fitted scaler.

### Key Observations & Limitations
1. **Class Imbalance Impact:** Class 0 (Benign) represents ~79.7% of the test partition (53,562 flows), while rare classes like Worms (29 flows, 0.043%) and Analysis (60 flows, 0.089%) have limited support. This produces a noticeable divergence between standard overall accuracy (91.41%) and balanced accuracy (53.75%).
2. **Rare Attack Confusion:** Extreme minority categories (e.g. Shellcode, Analysis, DoS) exhibit cross-category confusion with higher-volume attack categories (Exploits and Fuzzers), which share packet length and inter-arrival time distributions.
3. **Zero Data Leakage:** Because `test_mask.npy` is strictly held-out and mutually disjoint from the training partition, the reported metrics reflect true generalization performance on unseen traffic flows.
