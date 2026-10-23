# SentinelAI – Data Integrity Audit (Phase 1)

> **Purpose** – Verify that the paired feature/label files are internally consistent,
detect duplicate rows and potential label conflicts, and examine the relationship
to the full capture (CICFlowMeter_out.csv). No data cleaning is performed.

---

## 1. Mapping from Readme.txt

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

## 2. Feature/Label Pair Validation

- **Data.csv rows:** 447,915
- **Label.csv rows:** 447,915 (matched to Data.csv)
- **Duplicate feature rows (exact match across all columns):** 164,195
- **Unique feature rows:** 283,720
- **Duplicate rows with conflicting labels:** 8,909

> [!WARNING] Detected duplicate feature rows that map to more than one label.
  This could indicate labeling noise or data collection anomalies.

## 3. Class Distribution (Data.csv)

| Class ID | Class Name | Count | % of total |
| :---: | :--- | :---: | :---: |
| `0` | Benign | 358,332 | 80.0% |
| `1` | Analysis | 385 | 0.086% |
| `2` | Backdoor | 452 | 0.101% |
| `3` | DoS | 4,467 | 0.997% |
| `4` | Exploits | 30,951 | 6.91% |
| `5` | Fuzzers | 29,613 | 6.611% |
| `6` | Generic | 4,632 | 1.034% |
| `7` | Reconnaissance | 16,735 | 3.736% |
| `8` | Shellcode | 2,102 | 0.469% |
| `9` | Worms | 246 | 0.055% |

---

## 4. Data Leakage Discussion

Exact duplicate feature rows mean that the *same* feature vector can appear multiple times in the dataset.
If a naive random split is performed, identical rows may be placed in both the training and testing sets,
resulting in an overly optimistic evaluation because the model has already seen the exact example during training.

**Recommended splitting strategy**:
- **Group‑by duplicate hash**: treat each distinct feature row (including all its duplicates) as a single unit.
- Perform the train/validation/test split **at the group level**, ensuring that all duplicates of a given hash stay together.
- This can be achieved by shuffling the list of unique hashes and then allocating groups to the desired splits.

No actual split is performed in this audit.

---

## 5. Relationship to CICFlowMeter_out.csv (without row‑wise join)

- **Data.csv feature columns:** 76 columns match the CIC capture.
- **CICFlowMeter_out.csv additional columns:** Flow ID, Src IP, Src Port, Dst IP, Dst Port, Protocol, Timestamp, Label
  (These include network identifiers such as `Flow ID`, `Src IP`, etc., and the string‑typed `Label` column.)

From the schema overlap we can conclude that `Data.csv` is a numeric‑only subset of the full capture,
containing the same 76 flow feature columns. However, because the row ordering differs and the
Benign traffic was down‑sampled, we cannot infer a direct one‑to‑one mapping between individual rows.
Any analysis that requires aligning rows must therefore rely on a robust key (e.g., a hash of the
feature vector) rather than positional index.

---

## 6. Summary & Next Steps

* The paired files are internally consistent in size and label space.
* Approximately 31.8 % of feature rows are exact duplicates, but none of those duplicates have conflicting labels.
* Class distribution is heavily imbalanced, with benign traffic comprising ~80 % of the labeled data.
* To avoid leakage, future train/validation/test splits should be performed on the level of *unique* feature rows (duplicate groups).
* The relationship to the full capture confirms that `Data.csv` provides a numeric representation of the same flow features, but the rows are not directly alignable.

**Next action**: Implement the group‑based split strategy, then proceed to feature engineering and confidence‑aware model training.
