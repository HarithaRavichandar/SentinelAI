# Historical Exposure Investigation – Task 12.0.6

**Correction Note (2026‑11‑18):** Updated claims regarding candidate holdout overlap with validation partitions, refined exposure classifications, and fixed the description of validation vs. test evaluation in `scripts/evaluate_fresh_pipeline.py`.

---

## 1. Executive Summary
The candidate common holdout (40,686 rows) is **not a pristine, untouched test set**. Independent audit (Task 12.0.5) shows that the holdout overlaps substantial portions of the legacy and fresh **validation** partitions (see § 5). The holdout has **zero overlap with any training partition**. Moreover, the Fresh validation partition is used for policy‑calibration in `scripts/calibrate_fresh_policy.py`; therefore, rows overlapping that partition have been **exposed to calibration**. No evidence shows that these overlapping rows were used for model‑fitting or hyper‑parameter tuning. Consequently, the holdout cannot serve as an independent benchmark.

---

## 2. Legacy and Fresh Split‑Mask Usage
| Model | Partition | Mask file | Purpose in code |
|-------|-----------|----------|-----------------|
| Legacy | Train | `data/processed/train_mask.npy` | Loaded by legacy training scripts (not shown) to select rows for model fitting. |
| Legacy | Validation | `data/processed/val_mask.npy` | Loaded in `scripts/validate_model.py` (lines **126‑131**) for validation of the legacy model. |
| Legacy | Test | `data/processed/test_mask.npy` | Loaded in `scripts/validate_model.py` (lines **126‑131**) for final test‑set evaluation. |
| Fresh  | Train | `data/processed_fresh/train_mask_fresh.npy` | Loaded in `scripts/train_fresh_model.py` (lines **179‑182**) and asserted exclusive of val/test/conflict masks. |
| Fresh  | Validation | `data/processed_fresh/val_mask_fresh.npy` | Loaded in `scripts/calibrate_fresh_policy.py` (header lines **7‑9**) and used for policy calibration; also referenced by `scripts/evaluate_fresh_pipeline.py` gate checks (lines **75‑78**). |
| Fresh  | Test | `data/processed_fresh/test_mask_fresh.npy` | Unblinded **once** in `scripts/evaluate_fresh_pipeline.py` (lines **13‑14**) for the final frozen evaluation after all pre‑evaluation gates. |

Both pipelines also load `conflict_mask_fresh.npy` (8,909 rows) to exclude conflicting‑label groups from training and validation.

---

## 3. Source‑Level Evidence
### 3.1 Mask Loading & Partition Isolation
* **Fresh training masks** – `scripts/train_fresh_model.py`:
  * `train_mask = np.load(train_mask_path)` – line **179**
  * `val_mask = np.load(val_mask_path)` – line **180**
  * `test_mask = np.load(test_mask_path)` – line **181**
  * `conflict_mask = np.load(conflict_mask_path)` – line **182**
* **Fresh validation mask** – `scripts/calibrate_fresh_policy.py`:
  * Header explicitly states *"Loads validation partition ONLY"* (lines **7‑9**). The helper `load_features_and_labels` (imported at line **65**) reads `val_mask_fresh.npy` under the hood.
* **Fresh test mask** – `scripts/evaluate_fresh_pipeline.py`:
  * Unblinding documented in the header (lines **13‑14**).
  * Pre‑evaluation gate function `run_pre_evaluation_gate` (lines **75‑82**) runs **before** any test‑mask load.
* **Legacy masks** – `scripts/validate_model.py`:
  * `mask_file = split_dir / f"{split}_mask.npy"` (line **126**)
  * `mask = np.load(mask_file)` (line **130**) when `split="test"`.

### 3.2 Training Data Selection & Pre‑processing
* Row slicing for fresh training data – `scripts/train_fresh_model.py`:
  * `X_train_raw = df_data.loc[train_mask].copy()` – line **198**
  * `y_train = s_label.loc[train_mask].copy()` – line **199**
* Scaler fitting – `scripts/train_fresh_model.py`:
  * `scaler = StandardScaler()` – line **212**
  * `scaler.fit(X_train_raw)` – line **214**
* Model fitting – `scripts/train_fresh_model.py`:
  * `rf = RandomForestClassifier(... )` – lines **254‑260**
  * `rf.fit(X_train_scaled, y_train)` – line **261**

### 3.3 Validation & Test Evaluation (Corrected)
* **Fresh validation evaluation** – performed **before** the test mask is ever loaded:
  * The script first runs `run_pre_evaluation_gate` (lines **75‑82**) which checks metadata but does **not** load `test_mask_fresh.npy`.
  * Validation metrics are computed later using the **validation split** via `load_features_and_labels` with `split="val"` (invoked inside `scripts/evaluate_fresh_pipeline.py` around line **200‑250**, omitted here for brevity).
* **Fresh test‑set evaluation** – occurs **after** the gate checks:
  * The test mask is unblinded exactly once (lines **13‑14**) and the same metric functions (`evaluate_multiclass_metrics`, `evaluate_binary_argmax_baseline`, policy‑evaluation functions) are applied to the test data.
* **Legacy test evaluation** – `scripts/validate_model.py` uses `load_evaluation_data` (lines **115‑168**) which asserts no overlap with the legacy training mask (lines **150‑153**).

### 3.4 Policy Calibration (Validation‑Only)
* Validation‑only loading – `scripts/calibrate_fresh_policy.py` header (lines **7‑9**) asserts *"Loads validation partition ONLY"*.
* Safety guard `assert_test_isolation` (lines **68‑79**) verifies the script never references `test_mask_fresh.npy`.
* Threshold sweep – described in lines **18‑22**; actual sweep logic resides in `evaluate_two_stage_threshold_pair` (lines **124‑190**).

---

## 4. Historical Model‑Selection Exposure
| Evidence | Status | Comments |
|----------|--------|----------|
| **Legacy validation metrics** used to compare legacy vs fresh models (see `final_validation_comparison.md`). | **Confirmed** | The report documents metric values from the legacy validation partition. |
| **Fresh validation metrics** used to calibrate policy thresholds (`calibrate_fresh_policy.py`). | **Confirmed** | The script operates exclusively on the fresh validation mask (lines **7‑9**, **68‑79**). |
| **Fresh test‑set results** influencing model hyper‑parameters. | **Unknown** | No code path modifies the model after the test‑mask evaluation; the repo does not record whether test results were inspected for later tuning. |
| **Legacy test‑set results** feeding back into model development. | **Reasonable Inference** | `scripts/validate_model.py` evaluates the saved legacy model on the test mask, but there is no automated retraining logic; manual analysts could have consulted the numbers. |
| **Use of overlapping rows from candidate holdout in training step**. | **Confirmed Negative** | `verify_split_isolation` in `scripts/train_fresh_model.py` (lines **81‑85**) asserts zero overlap with any training mask. |
| **Use of overlapping rows from candidate holdout in Fresh validation (policy calibration)**. | **Confirmed** | Candidate holdout rows overlap Fresh validation (20,299 rows / 13,688 groups). Those rows were fed to `scripts/calibrate_fresh_policy.py` for calibration (lines **7‑9**). |
| **Direct use of candidate holdout rows for hyper‑parameter search or other calibration**. | **Unknown** | No explicit references to the candidate holdout appear in the inspected scripts. |

---

## 5. Correct Candidate Holdout Overlap Table
| Partition | Overlap Rows | Overlap Groups |
|---|---:|---:|
| Legacy train | 0 | 0 |
| Legacy val | **20,268** | **13,747** |
| Legacy test | **20,418** | **13,739** |
| Fresh train | 0 | 0 |
| Fresh val | **20,299** | **13,688** |
| Fresh test | **20,387** | **13,798** |

These numbers are taken from the verified audit report `reports/task_12_0_5_holdout_independence_audit.md` (sections **5‑6**).

---

## 6. Final Recommendation & Limitations
*The candidate common holdout cannot be treated as an untouched final test set.* Its substantial overlap with both legacy and fresh **validation** partitions (≈ 20 k rows each) means any evaluation that uses it is **not independent** of prior model development. Additionally, the Fresh validation overlap means those rows were **exposed to policy‑calibration**.

**Recommendation**
- **Do not** use the 40,686‑row holdout for definitive model‑comparison benchmarks.
- For a clean benchmark, generate a new split that excludes **all rows that appear in any prior training, validation, test, or calibration partition**, and verify isolation using the same audit methodology.

**Limitations**
- The analysis is limited to the source code and reports present in the repository; it cannot account for external notebooks, ad‑hoc scripts, or manual analyst decisions that may have consulted test results.
- Line‑level evidence is provided only for the scripts that were inspected; undiscovered pathways (e.g., custom Jupyter notebooks) are outside the scope of this report.
- The “Unknown” classification reflects the absence of programmatic evidence, not proof of absence.

---

*Prepared by Antigravity (AGY) – November 2026*