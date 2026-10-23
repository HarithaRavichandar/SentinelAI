# Random Forest Classifier – Validation Evaluation

**Accuracy:** 0.9296

**Macro‑F1:** 0.5893
**Weighted‑F1:** 0.9301

## Per‑class metrics
| Class | Precision | Recall | F1‑score | Support |
|------|-----------|--------|----------|---------|
| 0 | 0.992 | 0.983 | 0.988 | 53605 |
| 1 | 0.262 | 0.183 | 0.216 | 60 |
| 2 | 0.818 | 0.474 | 0.600 | 57 |
| 3 | 0.635 | 0.282 | 0.391 | 642 |
| 4 | 0.763 | 0.802 | 0.782 | 4716 |
| 5 | 0.638 | 0.813 | 0.715 | 4259 |
| 6 | 0.875 | 0.736 | 0.800 | 664 |
| 7 | 0.775 | 0.599 | 0.676 | 2826 |
| 8 | 0.148 | 0.244 | 0.184 | 315 |
| 9 | 0.704 | 0.442 | 0.543 | 43 |

## Confusion matrix
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

## Comparison with Logistic Regression baseline
- Logistic Regression validation accuracy: 0.8458
- Logistic Regression validation macro‑F1: 0.7330
- Logistic Regression validation weighted‑F1: 0.8800
- Random Forest validation accuracy: 0.9296
- Random Forest validation macro‑F1: 0.5893
- Random Forest validation weighted‑F1: 0.9301

**Note:** No claim of superiority is made unless the validation metrics clearly exceed the baseline.
