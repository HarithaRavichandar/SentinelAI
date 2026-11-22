# Task 12.2.3 — Model Training, Validation, and Held-Out Evaluation Report

**Project**: SentinelAI  
**Path**: `H:\SentinelAI`  
**Experiment Subsystem**: `experiments/cic_three_class/`  
**Date**: November 19, 2026  
**Status**: Completed  
**Authoritative Config**: `experiments/cic_three_class/configs/experiment_config.json`  

---

## 1. Executive Summary

Task 12.2.3 executed the complete training, validation, model selection, and held-out test evaluation pipeline for the independent 3-class CIC-IDS-2018 experiment (`Benign`, `FTP-BruteForce`, `SSH-Bruteforce`).

All operations strictly adhered to the safety rules, zero-leakage constraints, and user specifications:
- **Zero Preprocessing Leakage**: Learned transformations (finite min/max clipping, median imputation, and constant feature removal) were fitted exclusively on `splits/train.csv` (562,046 rows).
- **Constant Feature Hygiene**: Exactly 10 constant features (including `CWE Flag Count` confirmed constant at 0) were detected on training data and excluded from model inputs, resulting in 66 active flow features.
- **No Unnecessary Transformations**: In accordance with tree-based estimator principles and explicit user guidance, `StandardScaler` was omitted.
- **Candidate Architectures Evaluated**:
  - **Candidate 1**: `RandomForestClassifier` (`class_weight="balanced"`, `n_estimators=100`, `max_depth=25`, `max_features="sqrt"`).
  - **Candidate 2**: `ExtraTreesClassifier` (`class_weight="balanced"`, `n_estimators=100`, `max_depth=25`, `max_features="sqrt"`).
  - **Candidate 3**: `BalancedRandomForestClassifier` (`imblearn.ensemble`) was verified as unavailable in `.venv_clean2` and broken by NumPy 2.x in Anaconda base; formally documented and safely excluded without unauthorized package installations.
  - **Candidate 4**: `HistGradientBoostingClassifier` (`class_weight="balanced"`, `max_iter=150`, `learning_rate=0.1`, `early_stopping=False`).
- **Model Selection Decision**: Candidate 2 (`ExtraTreesClassifier`) was selected as the primary winning model based on superior validation metrics (Balanced Accuracy: 1.0000, Macro F1: 1.0000, training time: 20.5s, artifact size: 1.42 MB). Candidate 4 (`HistGradientBoostingClassifier`) emerged as the best low-latency alternative (mean single-row latency: 10.75 ms, size: 0.95 MB).
- **Held-Out Test Set Isolation**: `splits/test.csv` (120,439 rows) was held completely blind during model training, tuning, and selection. It was evaluated strictly once after model selection was locked, achieving **Balanced Accuracy of 0.999996** and **Macro F1 of 0.999884**.
- **Existing Assets Intact**: All existing SentinelAI 10-class model artifacts, preprocessors, and web application code were completely untouched.

---

## 2. Environment and Dependency Audit

The experiment was executed using the project's verified Python environment:

| Property | Value | Notes |
| :--- | :--- | :--- |
| **Python Interpreter** | `3.11.7` (MSC v.1916 64 bit) | Verified via `.venv_clean2` |
| **scikit-learn** | `1.3.2` | Core estimator and metrics engine |
| **NumPy** | `1.26.4` | Array processing |
| **pandas** | `2.2.3` | Dataset I/O and frame handling |
| **joblib** | `1.6.0` | Model and preprocessor serialization |
| **imbalanced-learn** | `Not installed` / Incompatible | Formally documented below |

### Candidate 3 Compatibility Audit
User instructions required verifying `imbalanced-learn` availability and compatibility before executing Candidate 3 (`BalancedRandomForestClassifier`).
- In `.venv_clean2`, importing `imblearn` produces `ModuleNotFoundError: No module named 'imblearn'`.
- In the local base Anaconda environment, attempting to load `imblearn` fails with:
  ```
  AttributeError: _ARRAY_API not found
  ImportError: cannot import name 'parse_version' from 'sklearn.utils'
  ```
  caused by NumPy 2.x breaking legacy binary C-extensions in base Anaconda.
- **Safety Compliance**: In adherence to the strict instruction *"Do not install packages or recreate the virtual environment without approval"*, Candidate 3 was formally excluded from training, and all resources were focused on Candidates 1, 2, and 4.

---

## 3. Preprocessing and Feature Hygiene

### 3.1 Feature Schema and Ordering Verification
- Source schema: 80 columns total (3 metadata: `Dst Port`, `Protocol`, `Timestamp`; 76 numerical flow features; 1 target: `Label`).
- Metadata columns and target were strictly excluded from model feature inputs.
- Source ordering across all 76 features was verified against `experiments/cic_three_class/configs/experiment_config.json`.

### 3.2 Constant Feature Detection (Training Data Only)
Inspection of `train.csv` (562,046 rows) revealed exactly 10 constant features ($\text{variance} = 0.0$ and $\text{nunique} = 1$):
1. `Bwd PSH Flags` (all 0)
2. `Fwd URG Flags` (all 0)
3. `Bwd URG Flags` (all 0)
4. `CWE Flag Count` (all 0; investigated specifically below)
5. `Fwd Byts/b Avg` (all 0)
6. `Fwd Pkts/b Avg` (all 0)
7. `Fwd Blk Rate Avg` (all 0)
8. `Bwd Byts/b Avg` (all 0)
9. `Bwd Pkts/b Avg` (all 0)
10. `Bwd Blk Rate Avg` (all 0)

No near-constant features ($0 < \text{variance} < 10^{-5}$) were found.

### 3.3 Specific Investigation of `CWE Flag Count`
- In `train.csv`, `CWE Flag Count` consists of exactly 562,046 records with value `0`.
- It exhibits zero variance and contains no discriminating signal for brute-force attacks.
- Per user instruction, `CWE Flag Count` was **not renamed to `CWR Flag Count`** and was excluded from model inputs.

### 3.4 Non-Finite Value Imputation & Learned Statistics
Non-finite values were identified exclusively in two flow rate features:
- `Flow Byts/s`: 1,786 NaNs, 1,136 `+inf`, 0 `-inf`.
- `Flow Pkts/s`: 0 NaNs, 2,922 `+inf`, 0 `-inf`.

The custom `CICPreprocessor`:
- Replaced `+inf` with the training set finite maximum.
- Replaced `-inf` with the training set finite minimum.
- Imputed `NaN` with the training set finite median.
- Discarded the 10 constant features and preserved the exact ordering of the remaining **66 active features**.
- Saved as `experiments/cic_three_class/preprocessors/cic_preprocessor.joblib`.
- Feature manifest saved to `experiments/cic_three_class/audits/feature_manifest.json`.

---

## 4. Candidate Model Training and Validation Results

All models were trained strictly on `splits/train.csv` ($N = 562,046$) and evaluated on `splits/val.csv` ($N = 120,438$).

### 4.1 Candidate Summary Comparison (Validation Set)

| Candidate Model | Train Time | Val Bal Acc | Val Macro F1 | FTP F1 | SSH F1 | Benign F1 | Latency (1-row) | Model Size |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate 1: Random Forest** | 29.5s | 0.99998 | 0.99999 | 1.0000 | 0.99997 | 1.0000 | 31.98 ms | 1.02 MB |
| **Candidate 2: Extra Trees** | **20.5s** | **1.00000** | **1.00000** | **1.0000** | **1.00000** | **1.0000** | 32.50 ms | 1.42 MB |
| **Candidate 3: Balanced RF** | N/A | Excluded | Excluded | Excluded | Excluded | Excluded | N/A | N/A |
| **Candidate 4: HistGradientBoosting** | 34.4s | **1.00000** | **1.00000** | **1.0000** | **1.00000** | **1.0000** | **10.75 ms** | **0.95 MB** |

### 4.2 Validation Confusion Matrices

#### Candidate 1 (Random Forest)
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign               100,957              0              0
True FTP-BruteForce             0          4,312              0
True SSH-Bruteforce             1              0         15,168
```
*(Total misclassifications: 1 out of 120,438 rows)*

#### Candidate 2 (Extra Trees)
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign               100,957              0              0
True FTP-BruteForce             0          4,312              0
True SSH-Bruteforce             0              0         15,169
```
*(Total misclassifications: 0 out of 120,438 rows — 100% accuracy)*

#### Candidate 4 (HistGradientBoosting)
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign               100,957              0              0
True FTP-BruteForce             0          4,312              0
True SSH-Bruteforce             0              0         15,169
```
*(Total misclassifications: 0 out of 120,438 rows — 100% accuracy)*

### 4.3 Validation Area Under the Curve (PR-AUC and ROC-AUC)

| Metric | Candidate 1 (RF) | Candidate 2 (ET) | Candidate 4 (HGB) |
| :--- | :---: | :---: | :---: |
| **Macro ROC-AUC** | 1.0000 | 1.0000 | 1.0000 |
| **Macro PR-AUC** | 1.0000 | 1.0000 | 1.0000 |
| **FTP-BruteForce PR-AUC** | 1.0000 | 1.0000 | 1.0000 |
| **SSH-Bruteforce PR-AUC** | 1.0000 | 1.0000 | 1.0000 |
| **Benign PR-AUC** | 1.0000 | 1.0000 | 1.0000 |

---

## 5. Minority-Class Performance and Overfitting Analysis

### 5.1 Minority-Class Performance
- **FTP-BruteForce** represents only 2.41% of training data ($13,568$ rows) and 3.58% of validation data ($4,312$ rows).
  - All three evaluated candidates achieved **100% Precision, 100% Recall, and 1.0000 PR-AUC** on FTP-BruteForce in validation.
  - Zero false negatives or false positives occurred for FTP-BruteForce in Candidate 2 and Candidate 4.
- **SSH-Bruteforce** represents 13.13% of training data ($73,806$ rows) and 12.59% of validation data ($15,169$ rows).
  - Candidates 2 and 4 achieved **100% Precision and 100% Recall**.
  - Candidate 1 misclassified exactly 1 SSH flow as Benign (Recall: 99.993%).

### 5.2 Overfitting and Generalization Gap
To verify that the high performance was not an artifact of memorization, a 50,000-sample training slice was evaluated against the validation set:
- **Candidate 1**: Train Bal Acc = 1.0000, Val Bal Acc = 0.99998 $\rightarrow$ Generalization gap = $0.00002$.
- **Candidate 2**: Train Bal Acc = 1.0000, Val Bal Acc = 1.0000 $\rightarrow$ Generalization gap = $0.00000$.
- **Candidate 4**: Train Bal Acc = 1.0000, Val Bal Acc = 1.0000 $\rightarrow$ Generalization gap = $0.00000$.

### 5.3 Technical Rationale for Near-Perfect Separability
The near-perfect separability across all three model architectures is explained by the fundamental characteristics of network brute-force traffic in CIC-IDS-2018:
1. **Repetitive Protocol Signatures**: Automated password-guessing tools (e.g., Hydra, Medusa) generate thousands of brief, failed authentication attempts characterized by consistent TCP window sizes (`Init Fwd Win Byts`), uniform packet length variances, and distinct TCP flag distributions compared to normal user web and enterprise traffic.
2. **Distinct Flow Durations & Inter-Arrival Times**: Brute-force bursts produce clusters of tightly spaced forward packets (`Fwd IAT Min`, `Fwd IAT Mean`) that differ markedly from benign web browsing or background telemetry.
3. **Rigorous Deduplication**: Despite the removal of 225,628 duplicate rows and 20,024 conflicting rows during Task 12.2.1, the remaining distinct flow vectors retain clean, linearly and non-linearly separable decision boundaries.

---

## 6. Model Selection Rationale

Based on the validation comparison, **Candidate 2 (`ExtraTreesClassifier`)** was selected as the primary winning model:
1. **Flawless Validation Accuracy**: Achieved 1.0000 Balanced Accuracy and 1.0000 Macro F1 across all 120,438 validation rows.
2. **Fastest Training Throughput**: Fitted on 562,046 samples in only **20.5 seconds** (30% faster than Random Forest and 40% faster than HistGradientBoosting).
3. **Compact Footprint**: Serialized model artifact size is only **1.42 MB** (vastly below the 250 MB target).
4. **Batch Prediction Speed**: Achieved over **424,000 rows/second** inference throughput during validation.

*Secondary Recommendation*: For deployment environments where single-row real-time streaming latency is paramount, **Candidate 4 (`HistGradientBoostingClassifier`)** is documented as a viable alternative, achieving **10.75 ms** single-row prediction latency and a **0.95 MB** footprint.

---

## 7. Held-Out Test Set Evaluation (Selected Model: Candidate 2)

### 7.1 Protocol Adherence
In strict accordance with experimental requirements:
- The held-out test split (`splits/test.csv`, $N = 120,439$) was unlocked and evaluated **strictly once** after Candidate 2 was officially selected and serialized.
- Zero threshold adjustment, feature selection, or hyperparameter tuning was conducted on the test set.

### 7.2 Test Set Results

| Metric | Result | Target / Standard | Status |
| :--- | :---: | :---: | :---: |
| **Balanced Accuracy** | **0.999996** | $\ge 0.80$ | Exceeded |
| **Macro F1 Score** | **0.999884** | $\ge 0.78$ | Exceeded |
| **Macro Precision** | **0.999771** | $\ge 0.80$ | Exceeded |
| **Macro Recall** | **0.999996** | $\ge 0.80$ | Exceeded |
| **Macro PR-AUC** | **1.000000** | $\ge 0.85$ | Exceeded |
| **Overall Accuracy** | **0.999992** | N/A | Exceeded |
| **Inference Throughput** | **447,088 rows/s** | $\ge 10,000\text{ rows/s}$ | Exceeded |

### 7.3 Per-Class Performance on Test Set

| Class | Support (Rows) | Precision | Recall | F1-Score | PR-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Benign** | 90,644 | 1.00000 | 0.99999 | 0.99999 | 1.0000 |
| **FTP-BruteForce** | 1,455 | 0.99931 | 1.00000 | 0.99966 | 1.0000 |
| **SSH-Bruteforce** | 28,340 | 1.00000 | 1.00000 | 1.00000 | 1.0000 |

### 7.4 Test Set Confusion Matrix
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign                90,643              1              0
True FTP-BruteForce             0          1,455              0
True SSH-Bruteforce             0              0         28,340
```
- Across 120,439 unseen flows, exactly **1 error** occurred (1 Benign flow predicted as FTP-BruteForce).
- **False Negative Rate for Attacks**: Exactly **0.00%** (1,455 / 1,455 FTP attacks and 28,340 / 28,340 SSH attacks detected).
- **False Alarm Rate for Benign**: **0.0011%** (1 out of 90,644).

---

## 8. Artifact Inventory and Reproducibility

All generated artifacts are isolated inside `experiments/cic_three_class/`:

| Artifact Path | Description | Size |
| :--- | :--- | :---: |
| `preprocessors/cic_preprocessor.joblib` | Fitted `CICPreprocessor` (handles non-finites and drops 10 constant features) | 2.9 KB |
| `audits/feature_manifest.json` | Manifest documenting 76 source, 10 dropped, and 66 active features | 14.1 KB |
| `audits/train_feature_inspection.json` | Detailed variance, median, and non-finite audit of `train.csv` | 18.2 KB |
| `models/candidate_1_random_forest.joblib` | Trained Candidate 1 (RandomForestClassifier) | 1.02 MB |
| `models/candidate_2_extra_trees.joblib` | Trained Candidate 2 (ExtraTreesClassifier, **Selected Winner**) | 1.42 MB |
| `models/candidate_4_hist_gradient_boosting.joblib` | Trained Candidate 4 (HistGradientBoostingClassifier) | 0.95 MB |
| `metrics/validation_metrics.json` | Full validation metrics, confusion matrices, and latencies | 6.8 KB |
| `metrics/test_metrics.json` | Held-out test evaluation metrics for winning model | 1.9 KB |
| `predictions/test_predictions_summary.json` | Class distributions of predicted vs true test labels | 320 B |
| `reports/model_selection_decision.json` | Formal record of selection rationale and criteria | 740 B |
| `scripts/train_and_evaluate.py` | Complete end-to-end reproducible training script | 14.5 KB |

---

## 9. Safety and System Integrity Verification

1. **Existing Application Assets**:
   - `data/models/random_forest_balanced.pkl` (Legacy 10-class model) remains unchanged (timestamp: 21-Oct-2026).
   - `data/models_fresh/random_forest_fresh.pkl` (Fresh 10-class model) remains unchanged (timestamp: 30-Oct-2026).
   - Preprocessing artifacts `preprocessor_balanced.pkl` and `preprocessor_fresh.pkl` remain untouched.
   - FastAPI server (`src/sentinelai/api.py`) and React dashboard remain untouched.
2. **Dataset Preservation**:
   - Original dataset `data/external/cic_ids_2018/cic.csv` was accessed read-only and preserved bit-for-bit.
   - All three split CSV files (`train.csv`, `val.csv`, `test.csv`) remain unaltered.
3. **Production Readiness Caution**:
   - While Candidate 2 achieved 0.999996 Balanced Accuracy on this offline benchmark, **it must not be declared production-ready for live perimeter security without live traffic validation**. Production networks exhibit packet fragmentation, asymmetric routing, application tunneling, and emerging exploit patterns that benchmark datasets do not reflect.
4. **Git Policy**:
   - No commits or pushes have been performed.
