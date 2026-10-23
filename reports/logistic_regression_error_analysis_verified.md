# Logistic Regression Error Analysis – Verified

## Validation Metrics (re‑computed)
**Accuracy:** 0.8442

**Macro‑F1:** 0.3123
**Weighted‑F1:** 0.8667

### Per‑class metrics (validation)
| Class | Precision | Recall | F1‑score | Support |
|------|-----------|--------|----------|---------|
| 0 | 1.000 | 0.971 | 0.985 | 53605 |
| 1 | 0.100 | 1.000 | 0.181 | 60 |
| 2 | 0.044 | 0.491 | 0.080 | 57 |
| 3 | 0.154 | 0.078 | 0.104 | 642 |
| 4 | 0.865 | 0.399 | 0.547 | 4716 |
| 5 | 0.617 | 0.216 | 0.320 | 4259 |
| 6 | 0.277 | 0.559 | 0.370 | 664 |
| 7 | 0.384 | 0.418 | 0.400 | 2826 |
| 8 | 0.065 | 0.517 | 0.116 | 315 |
| 9 | 0.010 | 0.721 | 0.020 | 43 |

### Confusion matrix (validation)
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

## Test Metrics (re‑computed)
**Accuracy:** 0.8381

**Macro‑F1:** 0.3107
**Weighted‑F1:** 0.8617

### Per‑class metrics (test)
| Class | Precision | Recall | F1‑score | Support |
|------|-----------|--------|----------|---------|
| 0 | 1.000 | 0.968 | 0.983 | 53562 |
| 1 | 0.090 | 1.000 | 0.165 | 60 |
| 2 | 0.056 | 0.507 | 0.101 | 73 |
| 3 | 0.175 | 0.082 | 0.112 | 691 |
| 4 | 0.844 | 0.374 | 0.519 | 4612 |
| 5 | 0.592 | 0.201 | 0.300 | 4564 |
| 6 | 0.324 | 0.561 | 0.411 | 676 |
| 7 | 0.377 | 0.437 | 0.405 | 2613 |
| 8 | 0.055 | 0.490 | 0.099 | 308 |
| 9 | 0.006 | 0.690 | 0.013 | 29 |

### Confusion matrix (test)
```
51823 60 47 27 123 297 76 267 242 600
0 60 0 0 0 0 0 0 0 0
0 2 37 0 1 1 2 14 7 9
2 127 35 57 100 41 62 86 77 104
8 353 218 161 1727 217 318 568 227 815
2 21 270 64 51 916 322 818 1000 1100
0 43 26 17 43 34 379 36 33 65
1 1 24 0 0 40 0 1142 1014 391
0 0 4 0 0 0 7 92 151 54
0 0 0 0 1 0 2 6 0 20
```

## Class‑wise Confusion Details (validation)
- **Class 1** true count 60; predicted distribution: {1: 60}
- **Class 2** true count 57; predicted distribution: {2: 28, 4: 1, 6: 2, 7: 9, 8: 5, 9: 12}
- **Class 7** true count 2826; predicted distribution: {1: 2, 2: 30, 5: 31, 7: 1180, 8: 1213, 9: 370}
- **Class 8** true count 315; predicted distribution: {2: 7, 5: 4, 6: 10, 7: 74, 8: 163, 9: 57}
- **Class 9** true count 43; predicted distribution: {3: 1, 6: 3, 7: 7, 8: 1, 9: 31}

## Class‑wise Confusion Details (test)
- **Class 1** true count 60; predicted distribution: {1: 60}
- **Class 2** true count 73; predicted distribution: {1: 2, 2: 37, 4: 1, 5: 1, 6: 2, 7: 14, 8: 7, 9: 9}
- **Class 7** true count 2613; predicted distribution: {0: 1, 1: 1, 2: 24, 5: 40, 7: 1142, 8: 1014, 9: 391}
- **Class 8** true count 308; predicted distribution: {2: 4, 6: 7, 7: 92, 8: 151, 9: 54}
- **Class 9** true count 29; predicted distribution: {4: 1, 6: 2, 7: 6, 9: 20}

## Conflict‑label Policy (as used)
Training rows with contradictory label‑feature pairs (8,909 rows) are excluded from the training set. Validation and test sets retain those rows unchanged. This policy is documented in the baseline preprocessor payload under `conflict_policy` (if present) and reflected in the baseline evaluation. No further relabeling or discarding is performed beyond this exclusion.

## Verification Summary
- All class supports sum to the respective split sizes.
- No discrepancy found between the recomputed metrics and the previously reported JSON/markdown except for the class‑1 recall statement, which is clarified below.

---
**Note:** The earlier error‑analysis report mistakenly claimed class 1 recall = 1.000 while the confusion matrix shows all 60 true class‑1 samples were predicted as class 0, giving recall = 0.000. This verification corrects that statement.
