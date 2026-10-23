# SentinelAI – Data Split Report

> **Purpose** – Produce a leak‑resistant split that keeps duplicate feature groups intact and documents the resulting class balance.

---

## 1. Class mapping (from Readme.txt)

| Numeric ID | Class Name |
| :---: | :--- |
| `0` | Benign |
| `1` | Analysis |
| `2` | Backdoor |
| `3` | DoS |
| `4` | Exploits |
| `5` | Fuzzers |
| `6` | Generic |
| `7` | Reconnaissance |
| `8` | Shellcode |
| `9` | Worms |

---

## 2. Overall class distribution (before split)

| Class ID | Count | % of total |
| :---: | :---: | :---: |
| `0` | 358,332 | 80.0% |
| `1` | 385 | 0.086% |
| `2` | 452 | 0.101% |
| `3` | 4,467 | 0.997% |
| `4` | 30,951 | 6.91% |
| `5` | 29,613 | 6.611% |
| `6` | 4,632 | 1.034% |
| `7` | 16,735 | 3.736% |
| `8` | 2,102 | 0.469% |
| `9` | 246 | 0.055% |

---

## 3. Duplicate‑group statistics

- Total rows: 447,915
- Unique exact feature groups: 305,602
- Rows in groups occurring >1 time: 164,195
- Duplicate excess rows (total‑unique): 142,313
- Groups with conflicting labels: 497
- Rows affected by label conflicts: 8,909
  - Example conflicting groups (up to 5):
    - group_id `16` size 26 labels (0, 5)
    - group_id `20` size 134 labels (0, 5)
    - group_id `25` size 2 labels (0, 8)
    - group_id `32` size 219 labels (0, 7)
    - group_id `35` size 2 labels (5, 8)

---

## 4. Split proportions (row counts)

- Target fractions: train 70.00%, val 15.00%, test 15.00%
- Actual rows – Training: 313,540 (70.00%)
- Validation: 67,187 (15.00%)
- Test: 67,188 (15.00%)

---

## 5. Class distribution per split

### Training

0: 251165, 1: 265, 2: 322, 3: 3134, 4: 21623, 5: 20790, 6: 3292, 7: 11296, 8: 1479, 9: 174

### Validation

0: 53605, 1: 60, 2: 57, 3: 642, 4: 4716, 5: 4259, 6: 664, 7: 2826, 8: 315, 9: 43

### Test

0: 53562, 1: 60, 2: 73, 3: 691, 4: 4612, 5: 4564, 6: 676, 7: 2613, 8: 308, 9: 29

---

## 6. Reproducibility

- Random seed used: `42`
- Deterministic algorithm; same seed yields identical splits.

---

## 7. Limitations

- Exact per‑class stratification is **not** performed – groups may contain multiple classes, so split proportions per class can deviate.
- Conflicting‑label groups are retained; they are reported above.
- No resampling or oversampling is performed – class imbalance persists.
