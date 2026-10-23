# Validation Comparison: Logistic Regression vs Random Forest

## Overall Metrics
| Model | Accuracy | Macro‑F1 | Weighted‑F1 |
|------|----------|----------|-------------|
| Logistic Regression | 0.8442 | 0.3123 | 0.8667 |
| Random Forest | 0.9296 | 0.5893 | 0.9301 |

## Per‑class Metrics (selected)
| Class | Model | Precision | Recall | F1‑score | Support |
|------|-------|-----------|--------|----------|---------|
| 0 | Logistic Regression | 1.000 | 0.971 | 0.985 | 53605 |
| 0 | Random Forest | 0.992 | 0.983 | 0.988 | 53605 |
| 1 | Logistic Regression | 0.100 | 1.000 | 0.181 | 60 |
| 1 | Random Forest | 0.262 | 0.183 | 0.216 | 60 |
| 2 | Logistic Regression | 0.044 | 0.491 | 0.080 | 57 |
| 2 | Random Forest | 0.818 | 0.474 | 0.600 | 57 |
| 3 | Logistic Regression | 0.154 | 0.078 | 0.104 | 642 |
| 3 | Random Forest | 0.635 | 0.282 | 0.391 | 642 |
| 4 | Logistic Regression | 0.865 | 0.399 | 0.547 | 4716 |
| 4 | Random Forest | 0.763 | 0.802 | 0.782 | 4716 |
| 5 | Logistic Regression | 0.617 | 0.216 | 0.320 | 4259 |
| 5 | Random Forest | 0.638 | 0.813 | 0.715 | 4259 |
| 6 | Logistic Regression | 0.277 | 0.559 | 0.370 | 664 |
| 6 | Random Forest | 0.875 | 0.736 | 0.800 | 664 |
| 7 | Logistic Regression | 0.384 | 0.418 | 0.400 | 2826 |
| 7 | Random Forest | 0.775 | 0.599 | 0.676 | 2826 |
| 8 | Logistic Regression | 0.065 | 0.517 | 0.116 | 315 |
| 8 | Random Forest | 0.148 | 0.244 | 0.184 | 315 |
| 9 | Logistic Regression | 0.010 | 0.721 | 0.020 | 43 |
| 9 | Random Forest | 0.704 | 0.442 | 0.543 | 43 |

## Confusion Matrices
### Logistic Regression
```
52033 45 39 38 101 281 89 258 161 560
0 60 0 0 0 0 0 0 0 0
0 0 28 0 1 0 2 9 5 12
3 121 36 50 102 33 46 91 64 96
14 327 227 168 1884 185 325 590 214 782
0 15 243 49 53 919 493 824 650 1013
2 33 32 18 37 36 371 42 29 64
0 2 30 0 0 31 0 1180 1213 370
0 0 7 0 0 4 10 74 163 57
0 0 0 1 0 0 3 7 1 31
```

### Random Forest
```
52715 13 3 9 131 661 4 57 12 0
12 11 0 4 33 0 0 0 0 0
1 0 27 0 11 13 0 5 0 0
11 4 0 181 278 120 12 27 8 1
98 13 2 43 3783 535 23 201 15 3
225 1 1 20 305 3463 22 172 50 0
12 0 0 10 64 73 489 10 2 4
66 0 0 13 291 400 5 1693 358 0
11 0 0 5 49 151 4 18 77 0
1 0 0 0 12 10 0 1 0 19
```

## Most Frequent Confusions (Random Forest)
| True Class | Predicted As | Count |
|-----------|--------------|-------|
| 0 | 5 | 661 |
| 4 | 5 | 535 |
| 7 | 5 | 400 |
| 7 | 8 | 358 |
| 5 | 4 | 305 |

## Classes with Lowest Recall (Random Forest)
| Class | Recall |
|------|--------|
| 1 | 0.183 |
| 8 | 0.244 |
| 3 | 0.282 |

## Model Configuration Checks
- Logistic Regression class_weight parameter: balanced
- Random Forest class_weight parameter: None

## Limitations & Observations
- Small‑support classes (e.g., 1, 2, 7, 8, 9) exhibit low recall, especially for Random Forest.
- Conflicting‑label groups (8,909 rows) were excluded from training for both models; they remain in validation, potentially hurting recall for minority attacks.
- Weighted‑F1 is high for both models due to dominance of majority classes; macro‑F1 better reflects performance on rare attacks.
- Random Forest shows higher overall accuracy but lower macro‑F1, indicating it favours majority classes.

## Recommendation for Next Experiment
- Explore a **class‑weighted Gradient Boosting** (e.g., XGBoost or LightGBM) to improve macro‑F1 while retaining high accuracy.
- Consider **over‑sampling** or **synthetic data generation** for the low‑support attack classes to boost recall.
- Keep the current conflict‑exclusion policy unchanged for comparability.

