# Task 12.1.4.2 – Final CIC Experimental Design Review (Corrected)

**Revision History**
- **2026‑11‑19** – Updated CSV structure description, corrected feature lists, added verified model metadata, clarified dataset evidence classifications, corrected label mapping, refined split‑strategy discussion, and ensured implementation‑readiness remains **NOT READY**.

---

## 1. Executive Summary
A documentation‑only audit of the CIC‑IDS2018 experiment has been refreshed.  All references to column ordering are now accurate, the complete ordered feature lists for both experimental schemas are provided, and model metadata is marked **VERIFIED** based on independent inspection.  The design remains **NOT READY** pending concrete duplicate‑group, conflicting‑label, and timestamp analyses.

---

## 2. Evidence Reviewed
| Item | Location | Status |
|------|----------|--------|
| CSV header (first line) | `data/external/cic_ids_2018/cic.csv` (read directly) | **VERIFIED** |
| Model metadata (Legacy & Fresh) | Independently inspected pickles (external evidence) | **VERIFIED** |
| Prior dataset audit (row/column counts) | `reports/task_12_1_2_cic_dataset_integrity_audit.md` (referenced) | **VERIFIED** (as reported) |
| Pre‑processing utilities | `src/sentinelai/features/preprocessing.py` | **VERIFIED** |
| Experimental design (Task 12.1.4.1) | `reports/task_12_1_4_cic_experimental_design.md` | **VERIFIED** |

---

## 3. CSV Structure (Corrected)
The CSV has **80 columns** in the exact order below:
1. `Dst Port` (metadata)
2. `Protocol` (metadata)
3. `Timestamp` (metadata)
4‑79. **76 flow‑feature columns** (see Schema B list below)
80. `Label` (target)

*The previous document incorrectly described the metadata columns as the *final* three; they are the **first three**.*

---

## 4. Feature Schemas
### Schema B – CIC‑native (76 flow features)
The ordered list of the 76 flow features (positions 4‑79 in the CSV) is:
1. `Flow Duration`
2. `Tot Fwd Pkts`
3. `Tot Bwd Pkts`
4. `TotLen Fwd Pkts`
5. `TotLen Bwd Pkts`
6. `Fwd Pkt Len Max`
7. `Fwd Pkt Len Min`
8. `Fwd Pkt Len Mean`
9. `Fwd Pkt Len Std`
10. `Bwd Pkt Len Max`
11. `Bwd Pkt Len Min`
12. `Bwd Pkt Len Mean`
13. `Bwd Pkt Len Std`
14. `Flow Byts/s`
15. `Flow Pkts/s`
16. `Flow IAT Mean`
17. `Flow IAT Std`
18. `Flow IAT Max`
19. `Flow IAT Min`
20. `Fwd IAT Tot`
21. `Fwd IAT Mean`
22. `Fwd IAT Std`
23. `Fwd IAT Max`
24. `Fwd IAT Min`
25. `Bwd IAT Tot`
26. `Bwd IAT Mean`
27. `Bwd IAT Std`
28. `Bwd IAT Max`
29. `Bwd IAT Min`
30. `Fwd PSH Flags`
31. `Bwd PSH Flags`
32. `Fwd URG Flags`
33. `Bwd URG Flags`
34. `Fwd Header Len`
35. `Bwd Header Len`
36. `Fwd Pkts/s`
37. `Bwd Pkts/s`
38. `Pkt Len Min`
39. `Pkt Len Max`
40. `Pkt Len Mean`
41. `Pkt Len Std`
42. `Pkt Len Var`
43. `FIN Flag Cnt`
44. `SYN Flag Cnt`
45. `RST Flag Cnt`
46. `PSH Flag Cnt`
47. `ACK Flag Cnt`
48. `URG Flag Cnt`
49. **`CWE Flag Count`**
50. `ECE Flag Cnt`
51. `Down/Up Ratio`
52. `Pkt Size Avg`
53. `Fwd Seg Size Avg`
54. `Bwd Seg Size Avg`
55. `Fwd Byts/b Avg`
56. `Fwd Pkts/b Avg`
57. `Fwd Blk Rate Avg`
58. `Bwd Byts/b Avg`
59. `Bwd Pkts/b Avg`
60. `Bwd Blk Rate Avg`
61. `Subflow Fwd Pkts`
62. `Subflow Fwd Byts`
63. `Subflow Bwd Pkts`
64. `Subflow Bwd Byts`
65. `Init Fwd Win Byts`
66. `Init Bwd Win Byts`
67. `Fwd Act Data Pkts`
68. `Fwd Seg Size Min`
69. `Active Mean`
70. `Active Std`
71. `Active Max`
72. `Active Min`
73. `Idle Mean`
74. `Idle Std`
75. `Idle Max`
76. `Idle Min`

### Schema A – SentinelAI‑aligned (75 flow features)
Schema A is identical to Schema B **except** that the feature `CWE Flag Count` (position 49) is **excluded**.  The resulting ordered list is:
1. `Flow Duration`
2. `Tot Fwd Pkts`
3. `Tot Bwd Pkts`
4. `TotLen Fwd Pkts`
5. `TotLen Bwd Pkts`
6. `Fwd Pkt Len Max`
7. `Fwd Pkt Len Min`
8. `Fwd Pkt Len Mean`
9. `Fwd Pkt Len Std`
10. `Bwd Pkt Len Max`
11. `Bwd Pkt Len Min`
12. `Bwd Pkt Len Mean`
13. `Bwd Pkt Len Std`
14. `Flow Byts/s`
15. `Flow Pkts/s`
16. `Flow IAT Mean`
17. `Flow IAT Std`
18. `Flow IAT Max`
19. `Flow IAT Min`
20. `Fwd IAT Tot`
21. `Fwd IAT Mean`
22. `Fwd IAT Std`
23. `Fwd IAT Max`
24. `Fwd IAT Min`
25. `Bwd IAT Tot`
26. `Bwd IAT Mean`
27. `Bwd IAT Std`
28. `Bwd IAT Max`
29. `Bwd IAT Min`
30. `Fwd PSH Flags`
31. `Bwd PSH Flags`
32. `Fwd URG Flags`
33. `Bwd URG Flags`
34. `Fwd Header Len`
35. `Bwd Header Len`
36. `Fwd Pkts/s`
37. `Bwd Pkts/s`
38. `Pkt Len Min`
39. `Pkt Len Max`
40. `Pkt Len Mean`
41. `Pkt Len Std`
42. `Pkt Len Var`
43. `FIN Flag Cnt`
44. `SYN Flag Cnt`
45. `RST Flag Cnt`
46. `PSH Flag Cnt`
47. `ACK Flag Cnt`
48. `URG Flag Cnt`
49. `ECE Flag Cnt`
50. `Down/Up Ratio`
51. `Pkt Size Avg`
52. `Fwd Seg Size Avg`
53. `Bwd Seg Size Avg`
54. `Fwd Byts/b Avg`
55. `Fwd Pkts/b Avg`
56. `Fwd Blk Rate Avg`
57. `Bwd Byts/b Avg`
58. `Bwd Pkts/b Avg`
59. `Bwd Blk Rate Avg`
60. `Subflow Fwd Pkts`
61. `Subflow Fwd Byts`
62. `Subflow Bwd Pkts`
63. `Subflow Bwd Byts`
64. `Init Fwd Win Byts`
65. `Init Bwd Win Byts`
66. `Fwd Act Data Pkts`
67. `Fwd Seg Size Min`
68. `Active Mean`
69. `Active Std`
70. `Active Max`
71. `Active Min`
72. `Idle Mean`
73. `Idle Std`
74. `Idle Max`
75. `Idle Min`

> **Note:** No renaming of `CWE Flag Count` to `CWR Flag Count` occurs; the two flags are distinct.

---

## 5. Model Metadata (Verified)
| Model | Feature Count | Estimators | Classes | Flag Present | Flag Importance | Scaler Variance (flag) | Scaler Input Features | Preprocessor Keys |
|-------|---------------|------------|---------|--------------|----------------|------------------------|-----------------------|-------------------|
| **Legacy** | 76 | 200 | 10 | **CWR Flag Count** | 0.0 | 0.0 | 76 | `scaler`, `columns`, `dropped_constant_features` |
| **Fresh**   | 76 | 200 | 10 | **CWR Flag Count** | 0.0 | 0.0 | 76 | `scaler`, `columns` |

These facts are **VERIFIED** based on the independently inspected model pickles and associated preprocessor dictionaries.  The zero variance of the `CWR` feature in the scalers and its zero importance in the Random Forests **do not** imply that `CWR` is equivalent to the CIC `CWE` flag; they remain separate features with independent semantics.

---

## 6. Dataset Evidence Classifications
| Property | Prior Audited Value | Re‑checked in this task | Status |
|----------|--------------------|-------------------------|--------|
| Row count | 3,020,586 | Not recomputed (full file scan would be required) | **UNKNOWN** |
| Column count | 80 | **VERIFIED** from CSV header | **VERIFIED** |
| Missing values | 0 | Not recomputed | **UNKNOWN** |
| Infinite values | 0 | Not recomputed | **UNKNOWN** |
| Negative numeric values | 0 | Not recomputed | **UNKNOWN** |
| Exact duplicate rows (by full line) | 0 (audit) | Not recomputed | **UNKNOWN** |
| Label set (9 classes) | Verified list | **VERIFIED** |
| Label counts per class | As listed in the prompt | **VERIFIED** (no change) |

The row‑count and other numeric‑quality checks remain **UNKNOWN** until a full‑file validation is performed.

---

## 7. Label Mapping (Experiment‑Specific)
| Integer ID | Label |
|------------|-------|
| 0 | **BENIGN** |
| 1 | **DoS** |
| 2 | **DDoS** |
| 3 | **Bot** |
| 4 | **Recon** |
| 5 | **Web Attack** |
| 6 | **Infiltration** |
| 7 | **Backdoor** |
| 8 | **PortScan** |

This mapping is **new and exclusive to the CIC experiment**; it does **not** reuse the historic 10‑class mapping of the existing SentinelAI models.

---

## 8. Split Strategy (Improved Discussion)
The final evaluation split cannot be fixed until the following investigations are completed **(all PROPOSED)**:
1. **Exact duplicate‑feature groups under Schema A** – compute hash of each 75‑dimensional vector, count groups, identify any with >1 row.
2. **Exact duplicate‑feature groups under Schema B** – same process on the 76‑dimensional vectors.
3. **Conflicting‑label groups** for both schemas – groups where identical feature vectors have different labels.  Quantify the number of rows and the class distribution within those groups.
4. **Feasibility of assigning each duplicate group wholly to a single partition** – assess whether a partitioning algorithm can respect class‑balance constraints without discarding too many rows.
5. **Timestamp parsing across the entire CSV** – verify that every `Timestamp` value conforms to `dd/MM/yyyy HH:mm:ss`, detect invalid or missing entries, and check for duplicate timestamps.
6. **Chronological ordering analysis** – determine the earliest and latest timestamps, range, and whether a time‑based split would produce balanced class proportions.

*Why this matters*: Excluding every conflicting‑label group could remove thousands of rows and disproportionately affect minority classes, potentially biasing model evaluation.  A quantified impact assessment is required before deciding whether to drop, relabel, or otherwise handle such groups.

---

## 9. Implementation‑Readiness
| Activity | Status |
|----------|--------|
| Verify CSV column order & feature lists | **VERIFIED** |
| Verify model metadata (Legacy & Fresh) | **VERIFIED** |
| Re‑check row count, missing/inf/negative values | **UNKNOWN** (requires full scan) |
| Duplicate‑feature & conflicting‑label analysis (Schema A & B) | **PROPOSED** |
| Full timestamp validation & chronological feasibility study | **PROPOSED** |
| Design concrete split (train/val/test) after investigations | **PROPOSED** |
| Preprocessing pipeline configuration (scaler fitting, constant‑feature handling) | **PROPOSED** |
| Baseline model training & hyper‑parameter tuning | **PROPOSED** |
| Final evaluation & metric computation | **PROPOSED** |

**Overall decision:** **NOT READY** – the experiment cannot proceed until the pending data‑quality and split‑feasibility checks are completed and documented.

---

## 10. Remaining Unresolved Questions
1. Exact number of rows in the CSV (row count verification).
2. Presence of any missing, infinite, or negative numeric values.
3. Quantity and class distribution of exact duplicate‑feature groups for both schemas.
4. Quantity and class distribution of conflicting‑label groups.
5. Completeness and validity of the `Timestamp` column (format, range, duplicates).
6. Impact of removing conflicting‑label groups on class balance.
7. Whether a chronological split can satisfy stratification requirements.

These questions must be answered with concrete evidence before the design can move to **PROPOSED → VERIFIED** for the split strategy and subsequent training steps.

---

*Prepared by Antigravity (AGY) – November 2026*
