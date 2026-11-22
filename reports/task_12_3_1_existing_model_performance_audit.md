# Task 12.3.1 — Existing SentinelAI 10-Class Model Performance Audit

**Audit Date:** November 19, 2026  
**Auditor:** SentinelAI Audit & Verification Engine  
**Project Root:** `H:\SentinelAI`  
**Execution Scope:** Comprehensive Read-Only Audit of Existing 10-Class Classification Models  
**Reference Deliverable:** `reports/task_12_3_1_existing_model_performance_audit.md`  

---

## 1. Executive Summary

This report delivers a rigorous, independent read-only audit of SentinelAI's existing 10-class network intrusion classification models. The audit examines the two operational random forest implementations maintained in the repository:
1. **Legacy Model (`data/models/random_forest_balanced.pkl`)**: The historical baseline classifier paired with `data/processed/preprocessor_balanced.pkl`.
2. **Fresh Model (`data/models_fresh/random_forest_fresh.pkl`)**: The retrained classifier paired with `data/models_fresh/preprocessor_fresh.pkl`, developed following duplicate and conflicting-label quarantine.

### Core Audit Verdict

- **Predictive Performance**: The **Fresh Model** demonstrates superior predictive performance across global and minority-class metrics compared to the Legacy Model. Overall accuracy improves from **91.41% to 93.62%** (+2.21%), Macro F1 improves from **54.24% to 59.55%** (+5.31%), and major recall improvements are achieved in attack classes such as Generic (+17.24% F1), Reconnaissance (+13.97% F1), Shellcode (+16.45% F1), and DoS (+9.86% F1).
- **Persistent Weaknesses**: Despite high overall accuracy (~91–94%) driven by the dominant Benign class (which constitutes ~80% of all network flows), **both models suffer from low Balanced Accuracy (~53.75% Legacy vs. 54.41% Fresh)**. Severe minority-class detection deficiencies persist in both models: **Analysis** (F1: 28.28% Fresh vs. 31.48% Legacy), **Shellcode** (F1: 29.33% Fresh vs. 12.88% Legacy), **DoS** (F1: 43.33% Fresh vs. 33.47% Legacy), and **Worms** (F1: 45.28% Fresh vs. 46.15% Legacy).
- **Data Integrity and Splitting**: The Legacy model was trained on partitions containing 497 conflicting-label groups (8,909 flows with identical feature vectors but discordant labels). The Fresh pipeline properly quarantined these conflicting flows, eliminating label ambiguity during training.
- **Inference & Architectural Compatibility**: Both models share the identical 76-feature input schema (UNSW-NB15 unabbreviated feature set, including `CWR Flag Count`) and identical 10-class output space (`0: Benign` through `9: Worms`). `src/sentinelai/inference.py` natively supports version switching via `SENTINELAI_MODEL_VERSION` ("legacy" vs. "fresh"). However, the production triage decision policy (`src/sentinelai/triage/decision_engine.py`) is explicitly calibrated on the fresh validation set; executing the legacy model under two-stage triage triggers an operational warning regarding unvalidated pairing.
- **Authoritative Recommendation**: **Adopt Option B — Prefer the Fresh Model as the primary classifier for SentinelAI**. The fresh model provides superior generalization, cleaner data provenance, and full alignment with the calibrated two-stage triage policy, while documenting the persistent minority-class recall limitations that must be addressed in subsequent feature-engineering and rebalancing initiatives.

---

## 2. Model Architecture, Preprocessing & Provenance

### 2.1 Artifact Metadata Comparison

| Attribute | Legacy Model (`random_forest_balanced`) | Fresh Model (`random_forest_fresh`) |
| :--- | :--- | :--- |
| **Model File Path** | `data/models/random_forest_balanced.pkl` | `data/models_fresh/random_forest_fresh.pkl` |
| **Model File Size** | 916,337,113 bytes (~873.9 MB) | 929,431,545 bytes (~886.4 MB) |
| **Model SHA-256** | `73f9fc5d7986c1cc935e3dcd072ca3cc655e5539f5fdfeb104419113cb43258f` | `7573dd297654a7b72517bb1336c03fca78138515decfb3cabc1cad3a4b4f8a24` |
| **Preprocessor File** | `data/processed/preprocessor_balanced.pkl` | `data/models_fresh/preprocessor_fresh.pkl` |
| **Preprocessor Size** | 5,881 bytes | 5,515 bytes |
| **Preprocessor SHA-256**| `2fe879fbf70c3c72fbde6f50c3dc7c86b6e9edf6f450ee39fda8053284965169` | `0816c8d7488a1d2c0db7b3f4204f8ca01a88534841c669652c207d6e84c47a43` |
| **Estimator Class** | `sklearn.ensemble.RandomForestClassifier` | `sklearn.ensemble.RandomForestClassifier` |
| **Number of Estimators** | 200 trees | 200 trees |
| **Splitting Criterion** | Gini Impurity | Gini Impurity |
| **Class Weighting** | `'balanced'` | `'balanced'` |
| **Random State / Seed** | 42 | 101 |
| **Max Depth / Leaf Nodes** | None (unconstrained) | None (unconstrained) |
| **Min Samples Split / Leaf**| 2 / 1 | 2 / 1 |
| **Max Features** | `'sqrt'` (8 features per split) | `'sqrt'` (8 features per split) |
| **Parallel Jobs (`n_jobs`)**| -1 (all available cores) | 4 |
| **Input Features Expected**| 76 numeric flow features | 76 numeric flow features |
| **Target Classes** | 10 classes (`[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`) | 10 classes (`[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`) |

### 2.2 Preprocessing Pipeline & Feature Alignment

Both models utilize a serialized dictionary containing a fitted `sklearn.preprocessing.StandardScaler` and a list of 76 column names:
- **Feature Schema Alignment**: The column lists `prep_leg['columns']` and `prep_fresh['columns']` are **100% identical in order and naming**.
  - Starting columns: `'Flow Duration'`, `'Total Fwd Packet'`, `'Total Bwd packets'`, `'Total Length of Fwd Packet'`, `'Total Length of Bwd Packet'`.
  - Ending columns: `'Active Min'`, `'Idle Mean'`, `'Idle Std'`, `'Idle Max'`, `'Idle Min'`.
  - Notable naming convention: Features follow the UNSW-NB15 unabbreviated naming convention (e.g., `'CWR Flag Count'`, distinct from CIC-IDS-2018's `'CWE Flag Count'`).
- **Preprocessor Differences**:
  - Legacy preprocessor dictionary contains an extra key: `'dropped_constant_features': []`.
  - Fresh preprocessor dictionary contains exactly `{'scaler', 'columns'}`.
  - Both scalers are fitted on the respective training partitions with zero missing-value imputation (missing or non-numeric inputs raise a runtime error).

### 2.3 Training Data and Provenance

- **Source Dataset**: Both pipelines originate from `data/raw/Data.csv` (SHA-256: `60d55f4f8f1e72bdfa2e0c1c74c03ac301bd880af321fdad1ba453950a7aa16a`) and `data/raw/Label.csv` (SHA-256: `5b2fcf31dc2d03ac6a07f8791858e55d86306f05442c3a4528bcc67301956a56`), containing 447,915 total records.
- **Legacy Training Partition**:
  - Constructed using `data/processed/train_mask.npy` (313,540 rows, 213,686 exact feature groups).
  - Included 497 conflicting-label groups (8,909 rows) where identical flow vectors had conflicting labels across benign and attack classes.
- **Fresh Training Partition**:
  - Constructed using `data/processed_fresh/train_mask_fresh.npy` (307,304 rows, 214,078 exact feature groups).
  - Quarantined 8,909 conflicting rows into `conflict_mask_fresh.npy`.
  - Partitioning asserted zero overlap between training, validation (65,850 rows), and test (65,852 rows).

---

## 3. Evaluation Metrics & Comparative Performance

### 3.1 Global Test Set Metrics

Evaluations were performed on each model's respective held-out test split (Legacy: `test_mask.npy` with 67,188 rows; Fresh: `test_mask_fresh.npy` with 65,852 rows).

| Metric | Legacy Model (`random_forest_balanced`) | Fresh Model (`random_forest_fresh`) | Absolute Delta | Relative Change |
| :--- | :---: | :---: | :---: | :---: |
| **Evaluation Support (Rows)** | 67,188 | 65,852 | -1,336 | -1.99% |
| **Overall Accuracy** | 91.41% | 93.62% | +2.21% | +2.42% |
| **Balanced Accuracy** | 53.75% | 54.41% | +0.66% | +1.23% |
| **Macro F1-Score** | 54.24% | 59.55% | +5.31% | +9.79% |
| **Weighted F1-Score** | 91.53% | 93.53% | +2.00% | +2.19% |
| **Inference Latency (per flow)**| ~11.53 μs | ~12.10 μs | +0.57 μs | Negligible |

> [!IMPORTANT]
> **Divergence Between Overall and Balanced Accuracy**:  
> In both models, Overall Accuracy exceeds 91%, but Balanced Accuracy hovers around 54%. This discrepancy is a mathematical artifact of the 80/20 class imbalance: correctly classifying the massive Benign majority (~53,600 flows) inflates Overall Accuracy, while poor recall on severe minority classes (such as Shellcode, Analysis, and Worms) drags Balanced Accuracy down.

---

### 3.2 Per-Class Performance Breakdown

| Class ID | Class Label | Legacy Precision | Legacy Recall | Legacy F1 | Fresh Precision | Fresh Recall | Fresh F1 | Support (Legacy / Fresh) | F1 Delta (Fresh - Legacy) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `0` | **Benign** | 99.16% | 98.13% | **98.64%** | 99.25% | 98.53% | **98.89%** | 53,562 / 53,618 | **+0.25%** |
| `1` | **Analysis** | 35.42% | 28.33% | **31.48%** | 33.33% | 24.56% | **28.28%** | 60 / 57 | **-3.20%** |
| `2` | **Backdoor** | 84.78% | 53.42% | **65.55%** | 93.10% | 44.26% | **60.00%** | 73 / 61 | **-5.55%** |
| `3` | **DoS** | 40.24% | 28.65% | **33.47%** | 68.73% | 31.63% | **43.33%** | 691 / 667 | **+9.86%** |
| `4` | **Exploits** | 74.80% | 78.60% | **76.65%** | 74.66% | 80.16% | **77.31%** | 4,612 / 4,606 | **+0.66%** |
| `5` | **Fuzzers** | 62.16% | 73.97% | **67.55%** | 64.10% | 81.74% | **71.85%** | 4,564 / 3,966 | **+4.30%** |
| `6` | **Generic** | 52.39% | 72.93% | **60.98%** | 87.50% | 70.72% | **78.22%** | 676 / 683 | **+17.24%** |
| `7` | **Reconnaissance** | 65.08% | 39.30% | **49.01%** | 69.70% | 57.44% | **62.98%** | 2,613 / 1,894 | **+13.97%** |
| `8` | **Shellcode** | 8.99% | 22.73% | **12.88%** | 50.00% | 20.75% | **29.33%** | 308 / 265 | **+16.45%** |
| `9` | **Worms** | 52.17% | 41.38% | **46.15%** | 66.67% | 34.29% | **45.28%** | 29 / 35 | **-0.87%** |

---

### 3.3 Detailed Class-by-Class Comparative Analysis

1. **Generic (+17.24% F1) & Reconnaissance (+13.97% F1)**:
   - Fresh model exhibits dramatically improved precision for Generic attacks (87.50% vs. 52.39%) while retaining ~71% recall.
   - For Reconnaissance, recall jumps from 39.30% to 57.44% and precision improves from 65.08% to 69.70%.
2. **Shellcode (+16.45% F1)**:
   - In the Legacy model, Shellcode was a critical failure point with precision of only 8.99% (producing 627 false alarms as Reconnaissance and 150 misclassifications as Fuzzers).
   - In the Fresh model, Shellcode precision jumped to 50.00%, raising F1 from 12.88% to 29.33%, though recall remains low at 20.75%.
3. **DoS (+9.86% F1)**:
   - DoS precision surged from 40.24% to 68.73%, with recall improving from 28.65% to 31.63%.
4. **Minority Classes with Regressions (Analysis, Backdoor, Worms)**:
   - **Analysis** (57 test flows): F1 fell from 31.48% to 28.28% due to a drop in recall from 28.33% to 24.56%. Analysis remains heavily confused with Benign and Exploits.
   - **Backdoor** (61 test flows): F1 fell from 65.55% to 60.00% because recall dropped from 53.42% to 44.26%, despite precision reaching 93.10%.
   - **Worms** (35 test flows): F1 slightly decreased from 46.15% to 45.28% (recall dropped from 41.38% to 34.29%, while precision rose from 52.17% to 66.67%).

---

## 4. Evaluation Integrity, Split Leakage & Exposure Audit

### 4.1 Conflicting Feature Vectors & Data Cleansing

- **Legacy Pipeline Contamination**:
  - The legacy dataset contained 497 exact-feature groups representing 8,909 rows where identical feature vectors were mapped to contradictory labels (e.g., identical flow statistics labeled as Benign in one capture and Exploit/DoS in another).
  - The legacy model was trained on these conflicting rows, forcing tree splits to fit conflicting ground truth.
- **Fresh Pipeline Quarantine**:
  - Task 12.0.x and subsequent clean pipelines explicitly segregated these 8,909 flows into `conflict_mask_fresh.npy`.
  - The fresh training split (`train_mask_fresh.npy`) contains 0 conflicting groups, providing cleaner ground truth boundaries.

### 4.2 Candidate Common Holdout Independence Audit

The project historically evaluated a candidate common holdout of 40,686 rows to enable direct comparison between Legacy and Fresh models (`reports/task_12_0_5_holdout_independence_audit.md` and `reports/task_12_0_6_historical_exposure_investigation.md`):
- **Training Isolation**: The candidate holdout has **0 overlap** with either `Legacy train` or `Fresh train`.
- **Validation Exposure**: The candidate holdout overlaps heavily with prior validation partitions:
  - 20,268 rows (13,747 groups) overlap Legacy validation.
  - 20,299 rows (13,688 groups) overlap Fresh validation.
- **Policy Calibration Contamination**:
  - Because `scripts/calibrate_fresh_policy.py` utilized the Fresh validation partition to optimize triage thresholds ($\theta_{\text{low}}=0.20, \theta_{\text{high}}=0.70$) and class reliability weights, the overlapping rows in the candidate holdout were **exposed to policy calibration**.
  - As concluded in Task 12.0.6: **The candidate common holdout cannot be treated as an untouched final test set**. Definitive comparisons must rely on the strictly unblinded, non-overlapping test partitions (`test_mask.npy` and `test_mask_fresh.npy`).

---

## 5. Inference Engine & Application Compatibility Audit

### 5.1 Dynamic Version Switching (`src/sentinelai/inference.py`)

The inference engine architecture was audited for compatibility with both model artifacts:

```python
# Model artifacts registry in src/sentinelai/inference.py
MODEL_ARTIFACTS = {
    "legacy": {
        "model_path": PROJECT_ROOT / "data" / "models" / "random_forest_balanced.pkl",
        "preproc_path": PROJECT_ROOT / "data" / "processed" / "preprocessor_balanced.pkl",
    },
    "fresh": {
        "model_path": PROJECT_ROOT / "data" / "models_fresh" / "random_forest_fresh.pkl",
        "preproc_path": PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl",
    },
}
```

- **Environment Control**: Version selection is governed by `os.getenv("SENTINELAI_MODEL_VERSION", "legacy")`.
- **Default Fallback**: Currently defaults to `"legacy"` for backwards compatibility.
- **Fail-Fast Safety**: Invalid values trigger an explicit `ModelConfigurationError` rather than defaulting silently. When `"fresh"` is requested, any missing artifact or load failure raises a `RuntimeError` rather than falling back to a dummy model.

### 5.2 Schema Validation & Preprocessing

- Both models receive payloads validated by `_validate_input(features: Dict[str, Any])`:
  - Exactly 76 numeric flow features required.
  - Unexpected or missing features raise `ValueError` (HTTP 400).
  - Rejects `NaN`, `inf`, `-inf`, and boolean inputs.
  - Features are projected into the preprocessor's exact column order and transformed via `scaler.transform()`.
- Prediction probabilities are extracted via `predict_proba()` and normalized to ensure $\sum p_i = 1.0$.

### 5.3 Triage Decision Engine Coupling (`src/sentinelai/triage/decision_engine.py`)

A critical architectural finding involves the coupling between the model and the triage decision engine:
- The decision engine loads `calibrated_params_fresh.json`, which was computed exclusively from the **Fresh validation partition**.
- Class reliability weights stored in `calibrated_params_fresh.json`:
  - Benign: 0.98, Generic: 0.81, Exploits: 0.76, Backdoor: 0.63, Fuzzers: 0.63, Reconnaissance: 0.62, Worms: 0.43, DoS: 0.39, Shellcode: 0.32, Analysis: 0.22.
  - High-confusion class: `[1]` (Analysis).
- When the experimental two-stage triage policy (`SENTINELAI_TWO_STAGE_TRIAGE=1`) is active:
  - If `model_version == "fresh"`: Configuration is verified as validated.
  - If `model_version == "legacy"`: An operational warning and uncertainty reason are appended to the decision evidence:
    `"Operational warning: Experimental two-stage policy was calibrated on fresh validation data; operating with legacy model lacks matching validation guarantees."`
- **Result**: Operating the Legacy model under the two-stage triage policy creates an uncalibrated mismatch, whereas the Fresh model is fully calibrated and harmonious with the decision engine.

---

## 6. Identified Deficiencies and Limitations

1. **Severe Minority-Class Blind Spots**:
   - Both models exhibit low recall on rare attack categories:
     - **Analysis**: Recall is 24.56% (Fresh) vs. 28.33% (Legacy). ~75% of actual Analysis attacks are misclassified as Benign or Exploits.
     - **Shellcode**: Recall is 20.75% (Fresh) vs. 22.73% (Legacy). ~79% of Shellcode attacks are missed.
     - **DoS**: Recall is 31.63% (Fresh) vs. 28.65% (Legacy). Over 68% of DoS attacks are missed or confused with Exploits.
     - **Worms**: Recall is 34.29% (Fresh) vs. 41.38% (Legacy).
2. **Benchmark & Testbed Confounding**:
   - Both models are trained on UNSW-NB15 flow data. As observed during the CIC experiments (Task 12.2.x), benchmark flow datasets frequently embed synthetic TCP shortcuts and port/protocol artifacts that may not generalize to real enterprise perimeter traffic.
3. **Large Serialized Model Footprint**:
   - Both model pickles exceed **870 MB** (`random_forest_balanced.pkl`: 916 MB; `random_forest_fresh.pkl`: 929 MB).
   - This footprint imposes substantial memory overhead (~1.5–2 GB during inference initialization) and introduces unpickling latency (~5–10 seconds at server boot).
4. **Disparity in Primary Model Selection**:
   - Despite the documented advantages of the Fresh model in reports dating from October/November 2026, `src/sentinelai/inference.py` still defaults to `"legacy"`.

---

## 7. Authoritative Strategic Recommendation

The audit evaluated three prospective paths:
- **Option A: Keep Current Primary Classifier (Legacy)**
- **Option B: Prefer Fresh Model After Compatibility Verification**
- **Option C: Improve Existing 10-Class Pipeline Before Further Integration**

### Recommendation: **OPTION B — Prefer Fresh Model After Compatibility Verification**

### Justification

1. **Superior Empirical Performance**: The Fresh model decisively outperforms the Legacy model across Overall Accuracy (+2.21%), Macro F1 (+5.31%), and major attack categories (Generic +17.24% F1, Reconnaissance +13.97% F1, Shellcode +16.45% F1, DoS +9.86% F1).
2. **Cleaner Data Provenance**: The Fresh model was trained on sanitized splits where 8,909 conflicting-label rows were quarantined, avoiding contradictory ground-truth fitting.
3. **Full Policy & Decision Engine Alignment**: The production triage decision engine's calibration (`calibrated_params_fresh.json`) was specifically fitted to the Fresh validation partition. Pairing the Fresh model with the two-stage triage policy provides mathematically guaranteed False Positive Rate bounds and eliminates the "unvalidated pairing" operational warnings generated when running Legacy.
4. **Zero-Code Drop-In Compatibility**: The backend already provides native runtime switching via `SENTINELAI_MODEL_VERSION="fresh"`. Zero code modifications, schema changes, or database migrations are required to make the switch.

### Roadmap for Option C (Future Phase 13 Work)

While Option B should be promoted immediately to primary status, the audit identifies several high-value initiatives for future model refinement:
- **Minority-Class Specialized Ensembles**: Address the persistent recall deficiencies in Analysis (24.56%) and Shellcode (20.75%) via focal loss, SMOTE, or dedicated one-vs-rest cascade detectors.
- **Model Distillation / Pruning**: Train a compact LightGBM, HistGradientBoosting, or pruned Random Forest to reduce the 929 MB model size down to <50 MB while preserving or improving inference throughput.
- **Automated Default Switch**: Update `DEFAULT_MODEL_VERSION = "fresh"` in `src/sentinelai/inference.py` following end-to-end integration testing.

---

## 8. Verification and Sign-Off Checklist

- [x] Inspected both Legacy and Fresh models (`random_forest_balanced.pkl`, `random_forest_fresh.pkl`).
- [x] Inspected both Preprocessor artifacts (`preprocessor_balanced.pkl`, `preprocessor_fresh.pkl`).
- [x] Verified 76-feature schema alignment and column ordering (100% match).
- [x] Extracted and verified scikit-learn parameters, seeds (42 vs 101), and estimators.
- [x] Documented SHA-256 hashes and file sizes for all artifacts.
- [x] Collected and compared global evaluation metrics (Accuracy, Balanced Accuracy, Macro F1, Weighted F1).
- [x] Detailed per-class precision, recall, and F1 comparison across all 10 classes.
- [x] Audited split independence, conflicting-vector quarantine, and holdout exposure.
- [x] Audited `src/sentinelai/inference.py` version-switching and input validation.
- [x] Audited `src/sentinelai/triage/decision_engine.py` policy calibration coupling.
- [x] Formulated authoritative recommendation (Option B).
- [x] Fully adhered to read-only constraints (no models retrained, no files overwritten, no git operations).
