# Random Forest – Final Test‑Set Evaluation

## Summary Metrics
- Accuracy: 0.9149
- Macro‑F1: 0.5457
- Weighted‑F1: 0.9160

## Per‑Class Metrics
| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| 0 | 0.9917 | 0.9812 | 0.9864 | 53562 |
| 1 | 0.3636 | 0.3333 | 0.3478 | 60 |
| 2 | 0.8864 | 0.5342 | 0.6667 | 73 |
| 3 | 0.4670 | 0.2865 | 0.3552 | 691 |
| 4 | 0.7468 | 0.7886 | 0.7671 | 4612 |
| 5 | 0.6213 | 0.7493 | 0.6793 | 4564 |
| 6 | 0.5272 | 0.7322 | 0.6130 | 676 |
| 7 | 0.6628 | 0.3934 | 0.4938 | 2613 |
| 8 | 0.0870 | 0.2208 | 0.1248 | 308 |
| 9 | 0.4783 | 0.3793 | 0.4231 | 29 |

## Confusion Matrix
Rows = true label, Columns = predicted label
|   | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 52556 | 20 | 1 | 8 | 156 | 676 | 56 | 71 | 18 | 0 |
| 1 | 12 | 20 | 0 | 5 | 23 | 0 | 0 | 0 | 0 | 0 |
| 2 | 0 | 0 | 39 | 1 | 16 | 8 | 0 | 7 | 1 | 1 |
| 3 | 14 | 2 | 0 | 198 | 290 | 124 | 14 | 40 | 9 | 0 |
| 4 | 86 | 13 | 3 | 36 | 3637 | 595 | 29 | 199 | 10 | 4 |
| 5 | 234 | 0 | 1 | 17 | 338 | 3420 | 332 | 177 | 40 | 5 |
| 6 | 10 | 0 | 0 | 7 | 72 | 72 | 495 | 10 | 8 | 2 |
| 7 | 67 | 0 | 0 | 147 | 280 | 454 | 9 | 1028 | 628 | 0 |
| 8 | 13 | 0 | 0 | 5 | 49 | 150 | 4 | 19 | 68 | 0 |
| 9 | 3 | 0 | 0 | 0 | 9 | 6 | 0 | 0 | 0 | 11 |

## Notes
- The preprocessing **scaler was loaded but NOT refitted**; the same feature scaling as during training is used.
- Conflicting‑label rows were excluded from training only; they remain in the test set, which may affect recall for some classes.
- No hyper‑parameter tuning or model selection was performed on the test data – this is a pure hold‑out evaluation.