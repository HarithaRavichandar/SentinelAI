# Task 12.2.2 — Model Experiment Selection and Compatibility Verification Specification

**Project Root**: `H:\SentinelAI`  
**Date**: 2026-11-19  
**Status**: COMPLETE (Specification & Compatibility Audit; No Models Trained)  
**Deliverable**: `reports/task_12_2_2_model_experiment_specification.md`  
**Configuration File**: `experiments/cic_three_class/configs/experiment_config.json`

---

## 1. Executive Summary & Objective

This document provides a formal, evidence-based model experiment specification for the three-class CIC-IDS2018 dataset partitioned during Task 12.2.1 / 12.2.1.1. 

### Core Architectural Separation
* **Existing SentinelAI System**: Uses a **10-class** intrusion detection model (`random_forest_balanced.pkl` / `random_forest_fresh.pkl`) trained on a 76-feature UNSW-NB15 schema with classes `[0: Benign, 1: Analysis, ..., 9: Worms]`. This production/demo triage system remains **strictly untouched**.
* **New CIC Experiment**: A completely independent, isolated **3-class** experimental pipeline located under `experiments/cic_three_class/` evaluating `Benign`, `FTP-BruteForce`, and `SSH-Bruteforce`.
* **Zero Direct Compatibility**: Due to severe feature naming discrepancies, label taxonomy differences (10 classes vs. 3 classes), and the semantic incompatibility between `CWR Flag Count` and `CWE Flag Count`, the existing models **cannot be evaluated or reused on the CIC dataset without training a dedicated CIC model**.

---

## 2. Phase 1 — Verified State & Feature Compatibility Audit

### 2.1 Verified Dataset Dimensions (from Task 12.2.1 / 12.2.1.1)
The completed audit and split pipeline established the following verified ground-truth numbers:
* **Original Source Rows**: 1,048,575 rows (SHA-256: `ACFF8BC61376EE031D80878EE6099E0B1A87A1BD711D8068298421418C9F8147`)
* **Exact Duplicate Rows Removed**: 225,628 rows (`is_dup=1`)
* **Unique Rows Remaining**: 822,947 rows
* **Conflicting Unique Rows Excluded**: 20,024 rows (across 7 feature groups with contradictory labels, totaling 169,775 rows in the CSV)
* **Eligible Unique Rows for Model Splits**: **802,923 rows** across **619,791 atomic feature groups**
* **Train Split**: 562,046 rows (70.00% of eligible unique rows; 440,155 groups)
* **Validation Split**: 120,438 rows (15.00% of eligible unique rows; 94,559 groups)
* **Test Split**: 120,439 rows (15.00% of eligible unique rows; 85,077 groups)
* **Schema Integrity**: All 3 split CSVs (`train.csv`, `val.csv`, `test.csv`) share the identical 80-column schema:
  - 3 metadata columns: `Dst Port`, `Protocol`, `Timestamp`
  - 76 numerical flow features: `Flow Duration` through `Idle Min`
  - 1 target column: `Label`

### 2.2 Existing Model Artifacts Inspection
Inspection of `data/models_fresh/train_fresh_metadata.json` and `src/sentinelai/inference.py` revealed the exact parameters of the existing SentinelAI models:
* **Model Type**: `RandomForestClassifier` (`n_estimators=200`, `class_weight='balanced'`, `random_state=101`)
* **Preprocessor**: `StandardScaler` fitted on 76 numerical features from `data/raw/Data.csv`.
* **Target Classes**: 10 classes (`0: Benign`, `1: Analysis`, `2: Backdoor`, `3: DoS`, `4: Exploits`, `5: Fuzzers`, `6: Generic`, `7: Reconnaissance`, `8: Shellcode`, `9: Worms`).

### 2.3 Feature Schema Comparison & The CWR vs. CWE Incompatibility

A line-by-line comparison between the existing SentinelAI model schema (`Data.csv` / `sample_features.json`) and the CIC-IDS2018 schema (`train.csv`) reveals that while both datasets contain **76 numerical flow features**, they are fundamentally incompatible:

1. **Abbreviation Discrepancies**:
   - Existing: `Total Fwd Packet`, `Total Bwd packets`, `Total Length of Fwd Packet`, `Flow Bytes/s`, `Packet Length Variance`, `FIN Flag Count`.
   - CIC: `Tot Fwd Pkts`, `Tot Bwd Pkts`, `TotLen Fwd Pkts`, `Flow Byts/s`, `Pkt Len Var`, `FIN Flag Cnt`.
2. **The Critical CWR vs. CWE Mismatch**:
   - Existing model requires: **`CWR Flag Count`** (Congestion Window Reduced, RFC 3168 TCP header bit).
   - CIC-IDS2018 contains: **`CWE Flag Count`** (Constant `0.0` across all 1,048,575 rows in `feature_quality_report.csv`).
   - `CWR Flag Count` is completely absent from the CIC dataset.
   - `CWE Flag Count` is not present in the existing SentinelAI model schema.
   - **Rule Enforced**: CWR and CWE are semantically and syntactically distinct. They must **never** be renamed, substituted, or aliased.
3. **Verdict**: **INCOMPATIBLE FOR DIRECT INFERENCE / ZERO-SHOT TRANSFER**.
   - Attempting to pass CIC flows into `InferenceEngine` will fail input schema validation.
   - The CIC experiment must train a dedicated, clean model using the verified 76 CIC flow feature names.

---

## 3. Phase 2 — Experimental Preprocessing Pipeline Specification

To guarantee leakage-free and robust model training, the experimental preprocessing pipeline is specified as follows:

```
[ train.csv ] -> Exclude Metadata & Target -> [ X_train (76 feats) ] -> Non-Finite Imputer (Fit) -> StandardScaler (Fit) -> [ Transformed X_train ]
                                                                                   │                           │
                                                                           Fitted Imputer Statistics    Fitted Scaler (Mean, Std)
                                                                                   │                           │
                                                                                   ▼                           ▼
[ val.csv   ] -> Exclude Metadata & Target -> [ X_val   (76 feats) ] ───────────► Apply Imputer ─────────────► Apply Scaler ───► [ Transformed X_val   ]
[ test.csv  ] -> Exclude Metadata & Target -> [ X_test  (76 feats) ] ───────────► Apply Imputer ─────────────► Apply Scaler ───► [ Transformed X_test  ]
```

### 3.1 Feature Exclusion
* **Metadata Columns**: `Dst Port`, `Protocol`, and `Timestamp` must be **strictly excluded** from model input features. Network port numbers and timestamps frequently cause severe temporal and topology leakage.
* **Target Column**: `Label` is excluded from feature matrices and converted via label encoding.
* **Model Inputs**: Exactly the 76 numerical flow features in their canonical order (`Flow Duration` to `Idle Min`).

### 3.2 Non-Finite Value Handling
`feature_quality_report.csv` identified non-finite values in only two columns:
* `Flow Byts/s`: 2,277 NaNs, 1,547 PosInfs
* `Flow Pkts/s`: 3,824 PosInfs

**Rules for Imputation**:
1. Imputation statistics must be computed **strictly on `X_train`**.
2. Any `NaN` value is replaced with the column **median** of finite values from `X_train`.
3. Any `+inf` value is clipped to the **finite maximum** observed in `X_train`.
4. Any `-inf` value is clipped to the **finite minimum** observed in `X_train`.
5. If a feature has no finite values in training, the pipeline must raise an error and abort.
6. The fitted imputer statistics are serialized into the preprocessor bundle and applied to validation and test sets without re-estimation.

### 3.3 Zero-Variance / Constant Features
`feature_quality_report.csv` identified 10 features with zero variance (`min == 0.0, max == 0.0`) across all 1,048,575 rows:
`Bwd PSH Flags`, `Fwd URG Flags`, `Bwd URG Flags`, `CWE Flag Count`, `Fwd Byts/b Avg`, `Fwd Pkts/b Avg`, `Fwd Blk Rate Avg`, `Bwd Byts/b Avg`, `Bwd Pkts/b Avg`, `Bwd Blk Rate Avg`.

* **Strategy**: Retain the complete 76-feature schema in the preprocessing pipeline. In `StandardScaler(with_mean=True, with_std=True)`, constant columns with variance 0 produce scale 1.0 (or output 0.0 without division by zero). In tree ensembles (Random Forest, Extra Trees), constant features are automatically ignored during node splitting. Retaining them maintains exact schema alignment with the raw CICFlowMeter specifications.

### 3.4 Feature Scaling
* **Method**: `StandardScaler` (z-score normalization: $\frac{x - \mu}{\sigma}$).
* **Fit Protocol**: `.fit(X_train)` strictly on training data.
* **Transform Protocol**: `.transform()` on `X_train`, `X_val`, and `X_test`.

### 3.5 Label Encoding
* Canonical integer mapping:
  - `Benign`: **0**
  - `FTP-BruteForce`: **1**
  - `SSH-Bruteforce`: **2**

### 3.6 Class Imbalance Strategy
* **Class Distribution in Training Set**:
  - `Benign`: 474,672 (84.45%)
  - `SSH-Bruteforce`: 73,806 (13.13%)
  - `FTP-BruteForce`: 13,568 (2.41%)
* **Recommended Strategy**: **Cost-Sensitive Learning (`class_weight="balanced"`)**.
  - Synthetic oversampling (e.g., SMOTE) or random undersampling on 560,000+ flows is computationally expensive, risks distorting realistic network traffic manifolds, and can induce synthetic boundary artifacts.
  - Setting `class_weight="balanced"` adjusts impurity calculations inversely proportional to class frequencies:
    $$w_c = \frac{N}{K \cdot N_c}$$
  - This natively prioritizes minority classes (`FTP-BruteForce`) during tree construction without altering the underlying data distribution.
* **Leakage Rule**: Under no circumstances should resampling or synthetic data generation be applied to validation or test splits.

---

## 4. Phase 3 — Recommended Model Candidates

Three competitive baseline models are recommended for evaluation:

| Candidate | Algorithm | Library & Version | Core Justification | Key Hyperparameters to Tune |
| :--- | :--- | :--- | :--- | :--- |
| **Candidate 1** | **Random Forest Classifier** | `sklearn.ensemble.RandomForestClassifier` (1.3.2) | Architectural baseline for SentinelAI. Highly robust to non-linear interactions and feature scaling. Provides native out-of-bag estimates and MDI feature importances. | `n_estimators`: [100, 200]<br>`max_depth`: [20, 30, None]<br>`min_samples_split`: [2, 5]<br>`class_weight`: ["balanced", "balanced_subsample"] |
| **Candidate 2** | **Extra Trees Classifier** | `sklearn.ensemble.ExtraTreesClassifier` (1.3.2) | Extreme randomization in split thresholds creates smoother decision boundaries, reduces variance, and trains 30–50% faster than standard Random Forest on large continuous feature spaces. | `n_estimators`: [100, 200]<br>`max_depth`: [20, 30, None]<br>`min_samples_split`: [2, 5]<br>`class_weight`: ["balanced"] |
| **Candidate 3** | **Histogram Gradient Boosting** | `sklearn.ensemble.HistGradientBoostingClassifier` (1.3.2) | Natively bins continuous features into 256 integer bins. Extremely fast training on 500k+ samples, lower memory footprint, and native support for missing values. | `max_iter`: [100, 200]<br>`learning_rate`: [0.05, 0.1]<br>`max_leaf_nodes`: [31, 63]<br>`class_weight`: ["balanced"] |

### Computational Cost & Deployment Considerations
* **Memory Bounding**: Training Random Forest on 562,046 samples with 76 features can produce large trees (~800 MB+). Setting `max_depth=30` and `min_samples_leaf=2` will constrain tree growth, ensuring the model size stays within the target ($\le 250\text{ MB}$) while preserving high classification accuracy.
* **Inference Latency**: To satisfy the engineering target ($\le 5\text{ ms}$ per sample), inference benchmarks must warm up the CPU and measure both single-row and batched prediction throughput.

---

## 5. Phase 4 — Evaluation Methodology & Validation Protocol

### 5.1 Metric Suite
Because network intrusion datasets suffer from significant class imbalance (Benign 84.5% vs. FTP-BruteForce 2.4%), standard accuracy is misleading. The evaluation will report:

1. **Primary Metric: Balanced Accuracy**
   $$\text{Balanced Accuracy} = \frac{1}{K} \sum_{k=1}^K \text{Recall}_k$$
2. **Macro F1, Macro Precision, Macro Recall** (unweighted mean across classes)
3. **Per-Class Metrics**: Precision, Recall, and F1-score for `Benign`, `FTP-BruteForce`, and `SSH-Bruteforce`.
4. **Confusion Matrix**: Full $3 \times 3$ error matrix.
5. **One-vs-Rest PR-AUC and ROC-AUC**:
   - **PR-AUC (Precision-Recall AUC)** is mandatory for `FTP-BruteForce` because ROC-AUC is overly optimistic on heavy class imbalances.
6. **Inference Latency**: Single-row median latency (1,000 runs) and 256-sample batch median latency (200 runs) after 10 warm-up runs on CPU.
7. **Model Artifact Size**: Physical file size on disk in megabytes.
8. **Feature Importance / Explainability**: Mean Decrease in Impurity (MDI) from tree ensembles and validation Permutation Importance.

### 5.2 Partition Usage Protocol
* **`train.csv` (562,046 rows)**: Exclusively used for fitting preprocessing transformations and model training.
* **`val.csv` (120,438 rows)**: Used for hyperparameter tuning, model comparison, threshold calibration, and candidate selection.
* **`test.csv` (120,439 rows)**: Held out completely untouched. Only the single selected best model will be evaluated once on `test.csv` to establish final generalization performance.

### 5.3 Investigation of Class-Distribution Differences Across Splits
In `split_stats.md`, the class proportions vary across the partitions:
* `Benign`: Train 84.45%, Val 83.82%, Test 75.26%
* `SSH-Bruteforce`: Train 13.13%, Val 12.59%, Test 23.53%
* `FTP-BruteForce`: Train 2.41%, Val 3.58%, Test 1.21%

#### Technical Explanation & Implications
* **Why did this occur?** This is an intrinsic consequence of **group-aware atomic splitting**. Network flows with identical 76 features (e.g., automated brute-force attacks executing identical packet bursts with different port numbers) were clustered into atomic groups to prevent data leakage. Attack flows tend to form very large identical-feature groups, whereas benign flows are more diffuse. Allocating entire discrete groups greedily causes natural variations in aggregate row percentages.
* **Implications**:
  - `FTP-BruteForce` in `test.csv` has 1,455 rows (1.21%), making minority recall especially sensitive.
  - `SSH-Bruteforce` is slightly more prevalent in `test.csv` (23.53%).
* **Protocol Directive**: **Do not modify the group-aware splits to artificially balance percentages.** Artificially forcing uniform percentages would require splitting identical feature groups across train and test, directly reintroducing the exact train/test data leakage that Task 12.2.1 was designed to eliminate.

---

## 6. Phase 5 — Experiment Execution Structure & Governance

### 6.1 Directory Hierarchy
All assets for this experiment are organized under `experiments/cic_three_class/`:

```
H:\SentinelAI\experiments\cic_three_class\
├── audits/                      # Audits from Task 12.2.1 (dataset_validation, duplicate_rows, etc.)
├── configs/                     # Experiment configurations (experiment_config.json)
├── logs/                        # Step-by-step timestamped execution logs
├── metrics/                     # JSON metrics, classification reports, confusion matrices
├── models/                      # Serialized model artifacts (.pkl)
├── predictions/                 # Out-of-fold and validation prediction probabilities (.npy)
├── preprocessors/               # Serialized preprocessor bundles (.pkl)
├── reports/                     # Task reports and markdown metric summaries
├── scripts/                     # Modular execution scripts for training, evaluation, benchmarking
└── splits/                      # Verified split CSVs (train.csv, val.csv, test.csv)
```

### 6.2 Experiment Configuration (`experiment_config.json`)
The configuration file has been written to:
`experiments/cic_three_class/configs/experiment_config.json`

It explicitly codifies:
* `random_seed`: 42
* Complete paths to `train.csv`, `val.csv`, and `test.csv`
* The exact 76 ordered feature names
* Label mappings (`Benign: 0`, `FTP-BruteForce: 1`, `SSH-Bruteforce: 2`)
* Preprocessing parameters (median imputation, infinite clipping, `StandardScaler`)
* Candidate models and hyperparameter search grids
* Acceptance targets (Balanced Accuracy $\ge 0.80$, Macro F1 $\ge 0.78$, Latency $\le 5\text{ ms}$, Size $\le 250\text{ MB}$)

---

## 7. Proposed Model Training & Evaluation Workflow (for Task 12.2.3)

When Task 12.2.3 is approved, execution should follow this four-stage pipeline:

```
[ Stage 1: Preprocessing ] ────────► Fit Preprocessor on train.csv ────────► Save preprocessors/cic_preprocessor.pkl
                                                 │
                                                 ▼
[ Stage 2: Model Training ] ───────► Fit Candidate Models on train.csv ────► Save models/*.pkl
                                                 │
                                                 ▼
[ Stage 3: Validation & Tuning ] ──► Evaluate Candidates on val.csv ───────► Select Best Model by Balanced Accuracy
                                                 │
                                                 ▼
[ Stage 4: Test Evaluation ] ──────► Final Evaluation on test.csv ────────► Generate metrics/ & reports/
```

1. **`scripts/train_cic_models.py`**:
   - Stream/load `train.csv`.
   - Fit `CICPreprocessor` (median imputer + finite max/min clipper + `StandardScaler`).
   - Fit Candidate 1 (Random Forest), Candidate 2 (Extra Trees), and Candidate 3 (HistGradientBoosting) with `class_weight='balanced'`.
   - Save models to `models/` and preprocessor to `preprocessors/`.
2. **`scripts/evaluate_cic_models.py`**:
   - Load `val.csv`.
   - Apply fitted preprocessor.
   - Generate predictions, probability scores, confusion matrices, and metrics.
   - Benchmark inference latency (single-row and batch).
   - Record validation results to `metrics/val_metrics.json`.
3. **Model Selection**:
   - Verify acceptance criteria on validation set.
   - Select winning architecture.
4. **Final Test Assessment**:
   - Evaluate winning model on `test.csv`.
   - Record unbiased final generalization metrics in `metrics/test_metrics.json`.

---

## 8. Risks, Assumptions, and Governance Classifications

### 8.1 Verified Facts from Repository
* `data/external/cic_ids_2018/cic.csv` contains 80 columns and 1,048,575 rows with SHA-256 `ACFF8BC61376...`.
* The splits contain 562,046 (train), 120,438 (val), and 120,439 (test) rows with 0 leakage across 619,791 unique groups.
* The existing production models expect `CWR Flag Count` and 10 UNSW-NB15 classes, which does not exist in the CIC dataset.
* 10 features in the CIC dataset are constant `0.0` across the entire 1,048,575 rows.

### 8.2 Technical Recommendations
* Use cost-sensitive learning (`class_weight="balanced"`) rather than resampling to address the 2.4% minority class (`FTP-BruteForce`).
* Evaluate Random Forest, Extra Trees, and HistGradientBoosting as baseline candidates.
* Constrain tree depth (`max_depth=25-30`) to keep model size under the 250 MB ceiling.

### 8.3 Assumptions Requiring Approval Before Task 12.2.3
* Acceptance of the proposed integer label mapping (`Benign=0, FTP-BruteForce=1, SSH-Bruteforce=2`).
* Agreement that `test.csv` remains strictly held out and will not be inspected or used for tuning during model development.

---

## 9. Safety and Scope Attestation

* **No models were trained** during this task.
* **No existing model artifacts** (`random_forest_balanced.pkl`, `random_forest_fresh.pkl`, `preprocessor_balanced.pkl`, `preprocessor_fresh.pkl`) were modified or overwritten.
* **No split files or source CSV files** were modified.
* **The application code, backend API, and frontend** remain completely untouched.
* **No Git commits or pushes** were performed.
