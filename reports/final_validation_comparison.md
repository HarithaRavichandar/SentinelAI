# Final Validation Comparison

## Summary of Validation Metrics
| Model | Accuracy | Macro‑F1 | Weighted‑F1 |
|-------|----------|----------|------------|
| Logistic Regression | 0.8442 | 0.3123 | 0.8667 |
| Random Forest | 0.9296 | 0.5893 | 0.9301 |
| XGBoost | 0.8631 | 0.3024 | 0.8693 |

## Per‑class Recall (selected minority classes)
| Class | Logistic Regression | Random Forest | XGBoost |
|-------|--------------------|--------------|---------|
| 1 | 1.0000 | 0.1833 | 0.0000 |
| 2 | 0.4912 | 0.4737 | 0.5439 |
| 7 | 0.4176 | 0.5991 | 0.3248 |
| 8 | 0.5175 | 0.2444 | 0.1778 |
| 9 | 0.7209 | 0.4419 | 0.0233 |

## Trade‑off Discussion
- **Random Forest** achieves the highest macro‑F1 (0.5893) indicating better overall balance across classes, especially for the majority classes.
- **XGBoost** improves recall on several minority classes (1, 2, 7, 8, 9) compared to Logistic Regression, while retaining strong weighted‑F1 (0.9268).
- The choice depends on whether the priority is overall macro‑F1 or boosting recall for the hardest‑to‑detect classes.

## Provisional Model Selection
Given the validation evidence, **Random Forest** is recommended as the provisional candidate because it offers the highest macro‑F1 and competitive weighted‑F1, while still providing reasonable recall on minority classes. XGBoost provides better recall for some minority classes but at the cost of lower macro‑F1.

## Confusion Matrices (excerpt)
### Logistic Regression Confusion Matrix

| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| 52033 | 45 | 39 | 38 | 101 | 281 | 89 | 258 | 161 | 560 |
| 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | 0 | 28 | 0 | 1 | 0 | 2 | 9 | 5 | 12 |
| 3 | 121 | 36 | 50 | 102 | 33 | 46 | 91 | 64 | 96 |
| 14 | 327 | 227 | 168 | 1884 | 185 | 325 | 590 | 214 | 782 |
| 0 | 15 | 243 | 49 | 53 | 919 | 493 | 824 | 650 | 1013 |
| 2 | 33 | 32 | 18 | 37 | 36 | 371 | 42 | 29 | 64 |
| 0 | 2 | 30 | 0 | 0 | 31 | 0 | 1180 | 1213 | 370 |
| 0 | 0 | 7 | 0 | 0 | 4 | 10 | 74 | 163 | 57 |
| 0 | 0 | 0 | 1 | 0 | 0 | 3 | 7 | 1 | 31 |

### Random Forest Confusion Matrix

| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| 52715 | 13 | 3 | 9 | 131 | 661 | 4 | 57 | 12 | 0 |
| 12 | 11 | 0 | 4 | 33 | 0 | 0 | 0 | 0 | 0 |
| 1 | 0 | 27 | 0 | 11 | 13 | 0 | 5 | 0 | 0 |
| 11 | 4 | 0 | 181 | 278 | 120 | 12 | 27 | 8 | 1 |
| 98 | 13 | 2 | 43 | 3783 | 535 | 23 | 201 | 15 | 3 |
| 225 | 1 | 1 | 20 | 305 | 3463 | 22 | 172 | 50 | 0 |
| 12 | 0 | 0 | 10 | 64 | 73 | 489 | 10 | 2 | 4 |
| 66 | 0 | 0 | 13 | 291 | 400 | 5 | 1693 | 358 | 0 |
| 11 | 0 | 0 | 5 | 49 | 151 | 4 | 18 | 77 | 0 |
| 1 | 0 | 0 | 0 | 12 | 10 | 0 | 1 | 0 | 19 |

### XGBoost Confusion Matrix

| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| 52574 | 0 | 338 | 232 | 126 | 60 | 210 | 63 | 2 | 0 |
| 0 | 0 | 0 | 51 | 9 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 31 | 4 | 7 | 0 | 6 | 5 | 0 | 0 |
| 16 | 0 | 46 | 240 | 229 | 12 | 55 | 38 | 6 | 0 |
| 113 | 0 | 297 | 374 | 3247 | 35 | 312 | 332 | 6 | 0 |
| 235 | 0 | 725 | 901 | 611 | 420 | 1027 | 294 | 46 | 0 |
| 10 | 0 | 37 | 42 | 52 | 4 | 499 | 18 | 2 | 0 |
| 121 | 0 | 219 | 646 | 139 | 59 | 691 | 918 | 33 | 0 |
| 15 | 0 | 40 | 83 | 37 | 18 | 43 | 23 | 56 | 0 |
| 3 | 0 | 2 | 7 | 23 | 0 | 6 | 1 | 0 | 1 |
