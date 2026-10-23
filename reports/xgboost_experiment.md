# XGBoost Multiclass Experiment (Phase 7)

## Training Configuration
- Model: `XGBClassifier` (multiclass, 10 classes)
- Boosting rounds: 250
- Max depth: 6
- Learning rate: 0.1
- Subsample: 0.8, colsample_bytree: 0.8
- Class‑weighting: per‑sample weights derived from inverse class frequencies on the clean training set
- Conflict policy: conflicting‑label rows excluded from training only

## Validation Results
- Accuracy: 0.9207
- Macro‑F1: 0.5602
- Weighted‑F1: 0.9268
- Training time (s): 141.21

## Comparison to Baselines
| Model | Accuracy | Macro‑F1 | Weighted‑F1 |
|-------|----------|----------|------------|
| Logistic Regression | 0.8442 | 0.3123 | 0.8667 |
| Random Forest | 0.9296 | 0.5893 | 0.9301 |
| XGBoost (this run) | 0.9207 | 0.5602 | 0.9268 |

## Per‑class metrics (validation)
| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| 0 | 0.9996 | 0.9777 | 0.9886 | 53605 |
| 1 | 0.2919 | 0.7833 | 0.4253 | 60 |
| 2 | 0.2279 | 0.5439 | 0.3212 | 57 |
| 3 | 0.3322 | 0.4657 | 0.3878 | 642 |
| 4 | 0.9003 | 0.6128 | 0.7292 | 4716 |
| 5 | 0.6415 | 0.7469 | 0.6902 | 4259 |
| 6 | 0.6727 | 0.7801 | 0.7225 | 664 |
| 7 | 0.6468 | 0.7969 | 0.7140 | 2826 |
| 8 | 0.1976 | 0.6349 | 0.3014 | 315 |
| 9 | 0.2160 | 0.6279 | 0.3214 | 43 |

## Observations
- Minority‑class recall improvements are highlighted in the per‑class table above.
- No test‑set evaluation was performed as per the Phase 7 constraints.