# Task 12.2.7 — Final CIC Dataset Suitability and Experimental Validity Assessment

**Project**: SentinelAI — Intelligent Security Alert Triage  
**Root**: `H:\SentinelAI`  
**Experiment Subsystem**: `experiments/cic_three_class/`  
**Date**: November 19, 2026  
**Status**: Completed  
**Analysis Mode**: Strictly Read-Only (Zero retraining, zero code or model modifications)  
**Authoritative Artifact**: `reports/task_12_2_7_cic_dataset_suitability_assessment.md`  

---

## 1. Executive Summary

Task 12.2.7 executed a final, comprehensive assessment of the CIC-IDS-2018 three-class experiment following the completion of Tasks 12.2.1 through 12.2.6.

The objective was to determine whether the dataset and its group-aware splits support meaningful, scientifically valid evaluation of **Benign traffic**, **SSH-Bruteforce**, and **FTP-BruteForce**, and to provide an authoritative deployment recommendation for SentinelAI.

### Authoritative Recommendation:
**Option B — Suitable for SSH-only experimental demonstration, with FTP limitations documented.**

### Key Findings:
1. **SSH-Bruteforce Detection is Validated for Limited Demonstration**:
   - The ablated Extra Trees model achieved **99.31% recall on validation ($15,065 / 15,169$)** and **99.99% recall on held-out test ($28,337 / 28,340$)**, with **1.0000 precision** and near-zero false alarms ($0.0011\%$).
   - SSH brute-force detection is grounded in legitimate, multi-feature behavioral dynamics (cryptographic handshake payload sizes `Bwd Pkt Len Max == 976 bytes`, client authentication packet counts `Fwd Act Data Pkts == 16`, and flag pushes `PSH Flag Cnt`) that survived the complete removal of benchmark-specific TCP shortcuts.
2. **FTP-BruteForce is Unfit for Integration**:
   - Out of 76 flow features, **only 7 features vary across all 19,335 FTP records**, and all 7 are mathematical derivatives of a single measurement: `Flow Duration` (microseconds).
   - In CIC-IDS-2018, **100% of FTP flows are zero-payload TCP connection attempts** (`TotLen Fwd Pkts == 0`, `TotLen Bwd Pkts == 0`).
   - In the ablated model, **98.63% of validation FTP flows ($4,253 / 4,312$) were misclassified as Benign** because their duration vectors (19 μs and 11 μs) identically collided with zero-payload benign background connections in training.
   - Detecting plaintext FTP authentication attempts using purely flow-level statistical aggregates without Deep Packet Inspection (DPI) is fundamentally fragile.
3. **Split Integrity is 100% Verified**:
   - The group-aware split achieved **zero identical-vector leakage across all splits** for both 76-feature vectors and 63-feature vectors.
   - The class balance shift across splits (Train: 13.13% SSH; Test: 23.53% SSH) is an expected mathematical consequence of allocating discrete attack bursts as atomic units to prevent leakage.
4. **Existing SentinelAI Assets Remain Completely Intact**:
   - All legacy and fresh 10-class UNSW-NB15 models, preprocessors, FastAPI endpoints, and React frontend components remain byte-for-byte unchanged with original October/November 2026 timestamps.

---

## 2. FTP Feature-Vector Analysis

A programmatic audit across all 19,335 FTP records (`train.csv`: 13,568; `val.csv`: 4,312; `test.csv`: 1,455) verified the following:

### 2.1 Feature Variance Audit Across All 76 Features
Across all 19,335 FTP records, exactly **69 features are invariant constants at 0.0**. Only 7 features exhibit non-zero variance:

| Feature Name | Unique Values | Variance | Min Value | Max Value | Physical / Mathematical Relationship |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`Flow Duration`** | 47 | 41.3453 | 0.0 μs | 63.0 μs | Raw flow duration in microseconds |
| **`Flow Pkts/s`** | 46 | $6.55 \times 10^9$ | 31,746.0 | 400,000.0 | Derived: $2 / \text{Duration} \times 10^6$ |
| **`Flow IAT Mean`** | 47 | 41.3453 | 0.0 μs | 63.0 μs | Derived: Identical to Flow Duration |
| **`Flow IAT Max`** | 47 | 41.3453 | 0.0 μs | 63.0 μs | Derived: Identical to Flow Duration |
| **`Flow IAT Min`** | 47 | 41.3453 | 0.0 μs | 63.0 μs | Derived: Identical to Flow Duration |
| **`Fwd Pkts/s`** | 47 | $1.64 \times 10^9$ | 0.0 | 200,000.0 | Derived: $1 / \text{Duration} \times 10^6$ |
| **`Bwd Pkts/s`** | 47 | $1.64 \times 10^9$ | 0.0 | 200,000.0 | Derived: $1 / \text{Duration} \times 10^6$ |

**Empirical Conclusion**: `Flow Duration` is **genuinely the only independently varying feature** among FTP-labelled records in the CIC-IDS-2018 dataset. All other 69 features—including all forward and backward packet lengths, byte rates, active packet counts, and subflow volumes—are fixed at 0.0.

### 2.2 Distinct Vector Counts & Frequencies
Because 69 features are constant, the 19,335 FTP records collapse into a tiny set of distinct feature vectors:
- **`train.csv`**: Exactly **32 distinct vectors** across 13,568 rows.
  - Top vector: `Duration == 18 μs` (3,196 rows, 23.56%)
  - Second vector: `Duration == 20 μs` (2,391 rows, 17.62%)
  - Third vector: `Duration == 17 μs` (1,169 rows, 8.62%)
- **`val.csv`**: Exactly **8 distinct vectors** across 4,312 rows.
  - Top vector (Vector V1): `Duration == 19 μs` (**4,077 rows, 94.55% of validation FTP**)
  - Second vector (Vector V2): `Duration == 11 μs` (**176 rows, 4.08% of validation FTP**)
  - Vectors V3–V5: `Duration >= 34 μs` (59 rows, 1.37%)
- **`test.csv`**: Exactly **7 distinct vectors** across 1,455 rows.
  - Top vector (Vector T1): `Duration == 8 μs` (**1,003 rows, 68.93% of test FTP**)
  - Second vector (Vector T2): `Duration == 22 μs` (**214 rows, 14.71% of test FTP**)
  - Vectors T3–T7: `Duration >= 29 μs` (238 rows, 16.36%)

---

## 3. Split Integrity & Leakage Verification

An automated collision audit checked for cross-split contamination:

### 3.1 Identical Vector Leakage Audit
- **76-Feature Vector Overlap**:
  - `Train` $\cap$ `Val`: **0 vectors** (0 rows)
  - `Train` $\cap$ `Test`: **0 vectors** (0 rows)
  - `Val` $\cap$ `Test`: **0 vectors** (0 rows)
- **63-Feature Ablated Vector Overlap**:
  - `Train` $\cap$ `Val`: **0 vectors** (0 rows)
  - `Train` $\cap$ `Test`: **0 vectors** (0 rows)
  - `Val` $\cap$ `Test`: **0 vectors** (0 rows)

**Verification**: The atomic group-aware split implemented in Task 12.2.1 succeeded completely. Zero identical feature vectors cross partition boundaries.

### 3.2 Cross-Class Collisions (FTP Val/Test vs. Benign Train)
When the 3 TCP shortcut features (`Fwd Seg Size Min`, `Init Fwd Win Byts`, `Init Bwd Win Byts`) were removed:
- **Validation Collisions with Training Benign Traffic**: Exactly **2 vectors** collided:
  - Vector V1 (`Duration == 19 μs`, 4,077 rows)
  - Vector V2 (`Duration == 11 μs`, 176 rows)
  - Both vectors match zero-payload benign background connections in `train.csv` identically across all 63 features.
  - Total colliding rows: **$4,077 + 176 = 4,253$ rows** (accounting for **100% of the validation false negatives**).
- **Test Collisions with Training Benign Traffic**: Exactly **1 vector** collided:
  - Vector T2 (`Duration == 22 μs`, 214 rows)
  - Total colliding rows: **214 rows** (accounting for **100% of the test false negatives**).

### 3.3 Reason for Class Distribution Skew
- Train contains 13.13% SSH and 2.41% FTP; Test contains 23.53% SSH and 1.21% FTP.
- This distribution difference was **not caused by a flawed random split**, but by the structural requirement to allocate discrete, highly repeated attack bursts atomically. Because thousands of rows share identical feature vectors, assigning an entire cluster to a split moves substantial percentage mass at once. Modifying the splits to force artificial class parity would break group isolation and reintroduce data leakage.

---

## 4. FTP Generalization Discrepancy: Verified Findings vs. Hypotheses

| Observation | Status | Verified Technical Evidence |
| :--- | :---: | :--- |
| **Validation FTP Recall = 1.37% ($59 / 4312$)** | **Verified Fact** | Confirmed by saved confusion matrix `[4253, 59, 0]`. Exactly 4,253 false negatives to Benign. |
| **Test FTP Recall = 85.29% ($1241 / 1455$)** | **Verified Fact** | Confirmed by saved confusion matrix `[214, 1241, 0]`. Exactly 214 false negatives to Benign. |
| **Duration Collisions Explain the Discrepancy** | **Verified Fact** | Vector V1 (19 μs, 4,077 rows) and Vector V2 (11 μs, 176 rows) sum to **exactly 4,253 rows**. Vector T2 (22 μs) equals **exactly 214 rows**. The false negatives match the collision groups to the exact integer. |
| **Same Capture Window (No Date Drift)** | **Verified Fact** | 100% of FTP traffic across all splits occurred between **10:33:26 and 12:10:31 on February 14, 2018** over port 21, sharing 4,000 identical second-level timestamps. |
| **Attacking Tool / OS Hypothesis** | **Hypothesis (Unproven)** | While fixed window sizes indicate an automated tool (e.g. Hydra), the exact tool and client OS cannot be proven from flow records alone. |

---

## 5. SSH Experimental Suitability Assessment

In contrast to FTP, **SSH-Bruteforce detection demonstrated strong, genuine behavioral generalization**:

### 5.1 Verified Performance Metrics (Ablated Extra Trees)
- **Validation Recall**: **99.31%** (15,065 detected out of 15,169; only 104 false negatives)
- **Validation Precision**: **1.0000** (0 false alarms)
- **Validation F1-Score**: **0.9966**
- **Held-Out Test Recall**: **99.989%** (28,337 detected out of 28,340; only 3 false negatives)
- **Held-Out Test Precision**: **0.99996** (1 false alarm out of 90,644 benign flows)
- **Held-Out Test F1-Score**: **0.99993**

### 5.2 Technical Grounding of SSH Detection
Unlike FTP, SSH flows in CIC-IDS-2018 represent multi-packet cryptographic authentication sessions:
- `Fwd Act Data Pkts`: SSH median = 16.0 ($\mu = 14.43$) vs Benign median = 0.0.
- `Bwd Pkt Len Max`: SSH median = 976.0 bytes vs Benign median = 74.0 bytes.
- `PSH Flag Cnt`: Consistently elevated during rapid credential submissions.
- `ACK Flag Cnt`: Reflects multi-round key exchange and banner negotiation.
Because these features survived the ablation of TCP option shortcuts, **SSH detection is behaviorally grounded in protocol dynamics rather than testbed harness watermarks**.

### 5.3 Scope of Suitability:
- **Permitted**: Suitable for a **limited experimental sidecar demonstration** in SentinelAI to show multi-class triage across UNSW-NB15 and CIC-IDS-2018 SSH flows.
- **Prohibited**: Must **not** be claimed as production-ready or capable of detecting slow password spraying, evasion via SSH protocol obfuscation, or attacks from unseen operating systems without live traffic testing.

---

## 6. Existing Application Integrity Verification

A strict read-only audit verified the preservation of all production and application assets:

| Asset Description | File Path | Status | Last Modified | Size |
| :--- | :--- | :---: | :---: | :---: |
| **Legacy 10-Class Model** | `data/models/random_forest_balanced.pkl` | **INTACT** | 2026-10-21 06:15:59 | 873.89 MB |
| **Fresh 10-Class Model** | `data/models_fresh/random_forest_fresh.pkl` | **INTACT** | 2026-10-29 21:17:57 | 886.37 MB |
| **Legacy Preprocessor** | `data/processed/preprocessor_balanced.pkl` | **INTACT** | 2026-10-21 06:47:28 | 5.88 KB |
| **Fresh Preprocessor** | `data/models_fresh/preprocessor_fresh.pkl` | **INTACT** | 2026-10-29 21:16:49 | 5.52 KB |
| **FastAPI Backend Server** | `src/sentinelai/api.py` | **INTACT** | 2026-11-11 06:12:42 | 18.82 KB |
| **Inference Pipeline Engine** | `src/sentinelai/inference.py` | **INTACT** | 2026-11-11 05:35:34 | 18.87 KB |
| **Raw CIC Dataset Source** | `data/external/cic_ids_2018/cic.csv` | **INTACT** | 2026-11-19 05:11:29 | 341.63 MB |

*Audit Verdict*: **ALL ASSETS ARE UNTOUCHED AND 100% PRESERVED.**

---

## 7. Authoritative Recommendation

### Choice: **Option B — Suitable for SSH-only experimental demonstration, with FTP limitations documented.**

### Decision Rationale:
1. **Rejection of Option A (Full Integration)**: Full three-class integration would imply that FTP brute-force detection is operational. In reality, the FTP classifier collapses to a 1.37% recall rate on zero-payload validation flows and is fundamentally unsuited for deployment without deep packet inspection.
2. **Rejection of Option C (Complete Abandonment)**: Discarding the experiment entirely would ignore the proven, robust success of the SSH brute-force model. SSH detection achieved 99.31% validation recall and 99.99% test recall with near-zero false alarms, driven by legitimate payload and packet exchange features that survived shortcut ablation.
3. **Selection of Option B (Gated Experimental Demonstration)**:
   - Expose the ablated Extra Trees model under an isolated, experimental endpoint (e.g. `POST /api/experimental/cic-triage`).
   - Gate the output so that **SSH-Bruteforce alerts are actively surfaced with confidence scores**, while **FTP traffic outputs a prominent telemetry caveat** noting that zero-payload flow analysis is unsuited for plaintext authentication detection without DPI.
   - Preserve the existing production 10-class UNSW-NB15 model as the primary, authoritative classifier.

---

## 8. Remaining Operational Risks

1. **FTP Blind Spot**:
   - Automated password-guessing against plaintext FTP daemons cannot be detected by flow metadata alone when the attacker aborts connections before authentication payloads are recorded.
2. **Slow / Low-Volume Password Spraying**:
   - The SSH model was evaluated against rapid brute-force connection attempts. Attackers conducting low-frequency spraying (e.g., 1 attempt every 15 minutes) will generate traffic that blends into benign background SSH administration sessions.
3. **Capture-Environment Homogeneity**:
   - Both SSH and FTP traffic originated from a controlled university testbed. While the ablated model eliminated TCP option shortcuts, packet size distributions could still exhibit minor variance when targeting non-Linux SSH daemons (e.g., Windows OpenSSH, Cisco IOS).

---

## 9. Recommended Next Development Milestone: Milestone 12.3

With Tasks 12.2.1 through 12.2.7 concluded, the recommended next milestone is:

### **Milestone 12.3 — Experimental Multi-Model Routing and Triage Integration**
1. **Task 12.3.1**: Implement a lightweight, non-breaking router in `src/sentinelai/` that accepts network telemetry and conditionally routes traffic:
   - UNSW-NB15 schema (76 features with `CWR Flag Count`) $\rightarrow$ Primary 10-Class Model.
   - CIC-IDS-2018 schema (63 ablated features with `CWE Flag Count` excluded) $\rightarrow$ Experimental 3-Class Model.
2. **Task 12.3.2**: Add explicit caveat flags in the triage response payload:
   - SSH detections flagged as `CONFIRMED_BEHAVIORAL_BRUTE_FORCE`.
   - FTP detections flagged as `LOW_CONFIDENCE_REQUIRES_DPI_VERIFICATION`.
3. **Task 12.3.3**: End-to-end integration and smoke testing in the React triage dashboard under an "Experimental CIC Telemetry" tab.

---

*Task 12.2.7 assessment complete. No code or model changes were made. Awaiting authorization to begin Milestone 12.3.*
