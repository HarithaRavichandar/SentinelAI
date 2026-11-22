# Holdout Independence Audit - Task 12.0.5

Audit timestamp: 2026-11-17 21:01:45

## 1. Dataset and Holdout Summary

- Total dataset rows: 447,915
- Total exact-feature groups: 305,602
- Conflicting-label groups: 497
- Conflicting-label rows: 8,909
- Candidate holdout rows: 40,686
- Candidate holdout groups: 27,486

### Candidate holdout class distribution

| Class ID | Rows |
|---:|---:|
| 0 | 33,311 |
| 1 | 31 |
| 2 | 31 |
| 3 | 348 |
| 4 | 2,829 |
| 5 | 2,381 |
| 6 | 398 |
| 7 | 1,179 |
| 8 | 161 |
| 9 | 17 |

## 2. Partition Integrity - Legacy

- **Legacy train:** 313,540 rows, 213,686 groups
- **Legacy val:** 67,187 rows, 45,808 groups
- **Legacy test:** 67,188 rows, 46,108 groups
- Expected covered rows: 447,915
- Actual covered rows: 447,915
- Duplicate groups split across partitions: 0

## 3. Partition Integrity - Fresh

- **Fresh train:** 307,304 rows, 214,078 groups
- **Fresh val:** 65,850 rows, 45,273 groups
- **Fresh test:** 65,852 rows, 45,754 groups
- Expected covered rows: 439,006
- Actual covered rows: 439,006
- Duplicate groups split across partitions: 0

## 4. Cross-Model Partition Overlap

| Legacy Partition | Fresh Partition | Overlap Rows | Overlap Groups |
|---|---|---:|---:|
| Legacy train | Fresh train | 216,485 | 149,795 |
| Legacy train | Fresh val | 45,551 | 31,585 |
| Legacy train | Fresh test | 45,465 | 31,956 |
| Legacy val | Fresh train | 45,419 | 31,984 |
| Legacy val | Fresh val | 10,077 | 6,881 |
| Legacy val | Fresh test | 10,191 | 6,866 |
| Legacy test | Fresh train | 45,400 | 32,299 |
| Legacy test | Fresh val | 10,222 | 6,807 |
| Legacy test | Fresh test | 10,196 | 6,932 |

Cross-model partition overlap is reported for transparency. It is not automatically treated as leakage because the two models were developed using different split assignments.

## 5. Candidate Holdout Overlap with Existing Partitions

| Partition | Overlap Rows | Overlap Groups |
|---|---:|---:|
| Legacy train | 0 | 0 |
| Legacy val | 20,268 | 13,747 |
| Legacy test | 20,418 | 13,739 |
| Fresh train | 0 | 0 |
| Fresh val | 20,299 | 13,688 |
| Fresh test | 20,387 | 13,798 |

## 6. Historical Exposure Assessment

**Status: UNKNOWN**

Keyword matches are leads for manual inspection. They do not prove that the candidate holdout was used or not used in model development.

### Files requiring manual inspection

- `scripts\audit_dataset.py` - keywords: validation, evaluation
- `scripts\calibrate_fresh_policy.py` - keywords: validation, test_mask, evaluation, hyperparameter
- `scripts\evaluate_fresh_pipeline.py` - keywords: validation, test_mask, test set, evaluation
- `scripts\inspect_dataset.py` - keywords: validation
- `scripts\inspect_features.py` - keywords: validation, test_mask, test set
- `scripts\prepare_fresh_dataset.py` - keywords: validation, test_mask, evaluation
- `scripts\train_fresh_model.py` - keywords: validation, test_mask, hyperparameter
- `scripts\validate_model.py` - keywords: validation, test_mask, evaluation
- `src\sentinelai\api.py` - keywords: validation, evaluation
- `src\sentinelai\inference.py` - keywords: validation
- `src\sentinelai\data\split.py` - keywords: validation, test_mask
- `src\sentinelai\features\preprocessing.py` - keywords: validation, test_mask, test set
- `src\sentinelai\models\logistic_regression.py` - keywords: validation, test_mask
- `src\sentinelai\models\random_forest.py` - keywords: validation, test_mask
- `src\sentinelai\triage\calibrated_params_fresh.json` - keywords: validation
- `src\sentinelai\triage\decision_engine.py` - keywords: validation, evaluation
- `reports\balanced_preprocessor_recovery.md` - keywords: validation, evaluation
- `reports\dashboard_data_lineage_audit.md` - keywords: validation
- `reports\data_integrity_audit.md` - keywords: validation, evaluation
- `reports\data_profile.md` - keywords: validation
- `reports\dependency_compatibility_audit.md` - keywords: validation, evaluation, model_selection
- `reports\feature_analysis.md` - keywords: validation, test set
- `reports\final_end_to_end_validation.md` - keywords: validation, test_mask, test set, evaluation
- `reports\final_evaluation_consistency_audit.md` - keywords: validation, evaluation
- `reports\final_fresh_evaluation_metrics.json` - keywords: validation, evaluation
- `reports\final_fresh_evaluation_report.md` - keywords: validation, test_mask, test set, evaluation
- `reports\final_validation_comparison.md` - keywords: validation
- `reports\fresh_policy_calibration_report.md` - keywords: validation, test_mask, evaluation
- `reports\fresh_split_report.md` - keywords: validation, evaluation
- `reports\github_final_safety_check.md` - keywords: validation, test_mask, evaluation, model_selection
- `reports\github_publication_preparation.md` - keywords: validation, evaluation, model_selection
- `reports\github_readiness_audit.md` - keywords: validation, evaluation, model_selection
- `reports\logistic_regression_error_analysis_verified.json` - keywords: validation
- `reports\logistic_regression_error_analysis_verified.md` - keywords: validation, test set, evaluation
- `reports\model_comparison_validation.json` - keywords: validation
- `reports\model_comparison_validation.md` - keywords: validation
- `reports\model_validation_metrics.json` - keywords: test_mask, evaluation
- `reports\model_validation_report.md` - keywords: validation, test_mask, evaluation
- `reports\november_finalization_audit.md` - keywords: validation, test_mask, evaluation
- `reports\random_forest_balanced_evaluation.md` - keywords: evaluation
- `reports\random_forest_balanced_final_test_report.md` - keywords: evaluation
- `reports\random_forest_balanced_subsample_evaluation.md` - keywords: evaluation
- `reports\random_forest_evaluation.md` - keywords: validation, evaluation
- `reports\random_forest_final_test_report.md` - keywords: test set, evaluation
- `reports\random_forest_flag_ratio_evaluation.md` - keywords: evaluation
- `reports\split_pipeline_review.md` - keywords: validation, test_mask, test set
- `reports\split_report.md` - keywords: validation
- `reports\split_report_test.md` - keywords: validation
- `reports\xgboost_experiment.md` - keywords: validation, evaluation
- `scratch\evaluate_holdout.py` - keywords: holdout, evaluation
- `scratch\holdout_class_distribution.py` - keywords: holdout
- `scratch\holdout_class_distribution_nopandas.py` - keywords: holdout
- `scratch\holdout_independence_audit.py` - keywords: holdout, validation, test_mask, test set, evaluation, hyperparameter, model_selection, threshold tuning
- `scratch\test_dashboard_e2e_lineage.py` - keywords: validation

## 7. Conclusion

**CONDITIONAL**

Structural checks passed, but historical exposure or validation/test overlap still requires investigation. Do not describe this holdout as an untouched final test set.

## 8. Audit Limitations

- This script does not train or modify any model.
- This script does not evaluate model predictions.
- This script does not establish historical non-use from keyword matches.
- The candidate holdout may overlap previous validation or test partitions. Such overlap must be considered before using it for model comparison.
- The holdout class distribution is highly imbalanced; do not rebalance or resample this evaluation population.
