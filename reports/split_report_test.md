# SentinelAI – Data Split Report

> **Purpose** – Produce a leak‑resistant split that keeps duplicate feature groups intact and documents the resulting class balance.

---

## 1. Class mapping (from Readme.txt)

| Numeric ID | Class Name |
| :---: | :--- |
| `0` | Benign |
| `1` | Malicious |

---

## 2. Overall class distribution (before split)

| Class ID | Count | % of total |
| :---: | :---: | :---: |
| `0` | 5 | 55.556% |
| `1` | 4 | 44.444% |

---

## 3. Duplicate‑group statistics

- Total rows: 9
- Unique exact feature groups: 6
- Rows in groups occurring >1 time: 6
- Duplicate excess rows (total‑unique): 3
- Groups with conflicting labels: 1
- Rows affected by label conflicts: 2
  - Example conflicting groups (up to 5):
    - group_id `1` size 2 labels (0, 1)

---

## 4. Split proportions (row counts)

- Target fractions: train 70.00%, val 15.00%, test 15.00%
- Actual rows – Training: 7 (77.78%)
- Validation: 1 (11.11%)
- Test: 1 (11.11%)

---

## 5. Class distribution per split

### Training

0: 4, 1: 3

### Validation

0: 1, 1: 0

### Test

0: 0, 1: 1

---

## 6. Reproducibility

- Random seed used: `42`
- Deterministic algorithm; same seed yields identical splits.

---

## 7. Limitations

- Exact per‑class stratification is **not** performed – groups may contain multiple classes, so split proportions per class can deviate.
- Conflicting‑label groups are retained; they are reported above.
- No resampling or oversampling is performed – class imbalance persists.
