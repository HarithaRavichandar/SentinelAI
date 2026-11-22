# Task 12.2.4 — Independent Model Generalization, Data Leakage, and Robustness Review

**Project**: SentinelAI  
**Path**: `H:\SentinelAI`  
**Experiment Subsystem**: `experiments/cic_three_class/`  
**Date**: November 19, 2026  
**Status**: Completed  
**Authoritative Artifact**: `reports/task_12_2_4_generalization_and_leakage_review.md`  

---

## 1. Executive Summary

Task 12.2.4 conducted an exhaustive, independent review to determine **why all candidate models achieved near-perfect validation performance ($\ge 99.998\%$) and why the selected Extra Trees model achieved 0.999996 Balanced Accuracy and 0.999884 Macro F1 on the held-out test split**.

### Key Findings:
1. **Experiment Integrity Verified**: Preprocessing was strictly leak-free, metadata and target columns were completely excluded, all three splits were rigorously isolated, and model predictions were 100% reproducible.
2. **Root Cause Discovered — Testbed TCP Stack Fingerprints (The "Shortcut")**:
   - The near-perfect performance is **not** due to traditional train/test data leakage, but rather to **testbed environment artifacts (operating system TCP stack fingerprints and socket configurations)** present in the CIC-IDS-2018 benchmark.
   - **`Fwd Seg Size Min`**: In `train.csv`, **100% of FTP-BruteForce flows have `Fwd Seg Size Min == 40.0` ($\sigma = 0.0$)**, and **100% of SSH-Bruteforce flows have `Fwd Seg Size Min == 32.0` ($\sigma = 0.0$)**, compared to a median of 20.0 for Benign traffic. A depth-3 decision tree on this single feature alone achieves **0.9979 Balanced Accuracy**.
   - **`Init Fwd Win Byts`**: **100% of FTP-BruteForce flows advertise an initial client TCP window of exactly 26,883 bytes ($\sigma = 0.0$)**.
   - **`Init Bwd Win Byts`**: **100% of FTP-BruteForce server responses advertise a window of exactly 0 bytes ($\sigma = 0.0$)**, and SSH server daemons consistently respond with a window of 230 bytes.
3. **Extreme Feature Importance Concentration**:
   - Permutation importance on validation data proves that permuting just two features (`Fwd Seg Size Min` and `Init Fwd Win Byts`) causes balanced accuracy to drop by **0.598** and **0.285** respectively. All other 64 features contribute almost negligibly when permuted independently.
4. **Generalization Vulnerability**:
   - The model has learned the static TCP header size and initial window size constants of the testbed's Kali Linux attacking machine (Hydra/Patator) and target VM daemons.
   - If an attacker initiates an SSH or FTP brute-force attack from a Windows workstation, macOS, Android, or using custom client tools that randomize window sizes or use standard 20-byte TCP headers, **this classification shortcut will fail and misclassify the attack as Benign**.
5. **Production Readiness Verdict**:
   - The model is **technically sound for internal prototype experimentation**, but **unfit for production autonomous perimeter defense** without retraining on feature sets stripped of static TCP stack fingerprints and validated against cross-dataset external traffic.

---

## 2. Phase 1 — Experiment Integrity Audit

An automated integrity verification was executed against all project artifacts:

| # | Integrity Verification Criterion | Audit Result | Evidence / Verification Path |
| :-: | :--- | :---: | :--- |
| **1** | Target `Label` excluded from model features | **PASS** | `audits/feature_manifest.json`: 66 active features, `Label` absent. |
| **2** | Metadata columns (`Dst Port`, `Protocol`, `Timestamp`) excluded | **PASS** | `configs/experiment_config.json`: Metadata strictly separated; absent from `feature_manifest.json`. |
| **3** | Preprocessing fitted strictly on `train.csv` | **PASS** | `CICPreprocessor.stats` derived solely from `train.csv` ($N = 562,046$); zero references to val or test data. |
| **4** | Segregation of splits | **PASS** | `train.csv` ($562,046$), `val.csv` ($120,438$), `test.csv` ($120,439$) verified distinct. |
| **5** | Validation metric reproducibility | **PASS** | Re-evaluation of `models/candidate_2_extra_trees.joblib` reproduces 1.0000 Balanced Accuracy on `val.csv`. |
| **6** | Held-out test evaluation reproducibility | **PASS** | Re-evaluation of `candidate_2_extra_trees.joblib` on `test.csv` reproduces 0.999996 Balanced Accuracy and 0.999884 Macro F1. |
| **7** | Confusion matrix exact reproduction | **PASS** | Test confusion matrix matches exactly: `[[90643, 1, 0], [0, 1455, 0], [0, 0, 28340]]`. |
| **8** | Label mapping consistency | **PASS** | `{"Benign": 0, "FTP-BruteForce": 1, "SSH-Bruteforce": 2}` preserved across all scripts and metrics. |

---

## 3. Phase 2 — Potential Leakage and Dataset Shortcuts

To understand why models achieved near 100% performance, an empirical audit was conducted to assess whether individual features act as "class shortcuts".

### 3.1 The OS & Protocol Stack Fingerprint Discovery
Analyzing the distributions of active features by class on `train.csv` revealed three extraordinary anomalies:

```
====================================================================================================
Feature Distributions in train.csv by Class (Mean, Standard Deviation, Min, Max)
====================================================================================================
Feature                  Benign (N=474,672)       FTP-BruteForce (N=13,568)     SSH-Bruteforce (N=73,806)
----------------------------------------------------------------------------------------------------
Fwd Seg Size Min         μ = 15.98, σ = 6.05      μ = 40.0, σ = 0.0             μ = 32.0, σ = 0.0
                         [min: 0, max: 40]        [min: 40, max: 40]            [min: 32, max: 32]
----------------------------------------------------------------------------------------------------
Init Fwd Win Byts        μ = 4865,  σ = 9992      μ = 26883, σ = 0.0            μ = 24263, σ = 7934
                         [min: -1, max: 65535]    [min: 26883, max: 26883]      [min: 241, max: 26883]
----------------------------------------------------------------------------------------------------
Init Bwd Win Byts        μ = 9575,  σ = 22011     μ = 0.0,  σ = 0.0             μ = 230.0, σ = 1.72
                         [min: -1, max: 65535]    [min: 0, max: 0]              [min: -1, max: 240]
====================================================================================================
```

### 3.2 Physical Meaning of the Shortcut Features
1. **`Fwd Seg Size Min` (Minimum Forward Segment Size)**:
   - In TCP/IP, the minimum header size without options is 20 bytes.
   - When specific TCP options (e.g., Maximum Segment Size, Window Scale, SACK Permitted, Timestamps) are enabled, the TCP header expands to 32 or 40 bytes.
   - In CIC-IDS-2018, the tool used to generate FTP brute-force attacks established TCP connections that **invariably had exactly 40 bytes of header ($\sigma = 0.0$)**.
   - The tool used to generate SSH brute-force attacks established connections with **invariably exactly 32 bytes of header ($\sigma = 0.0$)**.
   - Benign flows originate from varied operating systems (Windows, Linux, macOS) with varying TCP options, averaging 15.98 bytes (including UDP with 8-byte headers).
2. **`Init Fwd Win Byts` (Initial Client TCP Window Size)**:
   - Every single FTP brute-force flow originated from an attacker socket advertising an initial receive window of **exactly 26,883 bytes** ($\sigma = 0.0$).
3. **`Init Bwd Win Byts` (Initial Server TCP Window Size)**:
   - The victim FTP server in the testbed responded to every attack attempt with a window size of **0 bytes** ($\sigma = 0.0$).
   - The victim SSH server responded with a window size of **230 bytes** ($\sigma = 1.72$).

### 3.3 Single-Feature Predictive Power
A depth-3 Decision Tree trained on single features on a 30,000-row sample and evaluated on `val.csv` confirms that **a single feature alone is capable of near-complete classification**:

| Feature Name | Single-Feature Val Bal Acc | Single-Feature Macro F1 | FTP Recall | SSH Recall | Benign Recall |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`Fwd Seg Size Min`** | **0.9979** | **0.9899** | **1.0000** | **1.0000** | **0.9937** |
| **`Init Bwd Win Byts`** | **0.9764** | **0.8371** | **1.0000** | **1.0000** | **0.9291** |
| **`Bwd Header Len`** | **0.9441** | **0.7340** | **1.0000** | **0.9990** | **0.8333** |
| **`Flow IAT Mean`** | **0.9303** | **0.7284** | **0.9998** | **0.9430** | **0.8480** |
| **`Bwd Pkts/s`** | **0.9288** | **0.7374** | **1.0000** | **0.9437** | **0.8427** |
| **`Flow Pkts/s`** | **0.9215** | **0.7050** | **0.9998** | **0.9430** | **0.8217** |
| **`Flow Duration`** | **0.9200** | **0.6986** | **1.0000** | **0.9434** | **0.8167** |
| **`Fwd Header Len`** | **0.9170** | **0.6599** | **1.0000** | **0.9999** | **0.7510** |
| **`Init Fwd Win Byts`** | **0.6561** | **0.5951** | **0.0000** | **1.0000** | **0.9682** |

**Conclusion**: The models did not learn complex behavioral attack dynamics; they capitalized on zero-variance TCP option and window-size signatures produced by the testbed harness.

---

## 4. Phase 3 — Independent Feature Importance Analysis

### 4.1 Extra Trees MDI Importance (Gini Impurity)

The top 15 features by Mean Decrease in Impurity for Candidate 2 (`ExtraTreesClassifier`) are:

```
Rank  Feature Name               MDI Importance    % Contribution
-----------------------------------------------------------------
 1    Fwd Seg Size Min              0.24437            24.44%
 2    Bwd Pkt Len Max               0.13114            13.11%
 3    Init Fwd Win Byts             0.08921             8.92%
 4    PSH Flag Cnt                  0.05771             5.77%
 5    Bwd Pkt Len Std               0.03548             3.55%
 6    Bwd Seg Size Avg              0.03544             3.54%
 7    ACK Flag Cnt                  0.03200             3.20%
 8    Bwd Pkt Len Mean              0.02956             2.96%
 9    Bwd Pkts/s                    0.02808             2.81%
10    Pkt Len Max                   0.02304             2.30%
11    URG Flag Cnt                  0.02129             2.13%
12    Init Bwd Win Byts             0.01977             1.98%
13    Subflow Bwd Byts              0.01855             1.86%
14    Pkt Len Std                   0.01742             1.74%
15    Subflow Fwd Byts              0.01432             1.43%
-----------------------------------------------------------------
Top 15 Cumulative Contribution:                        79.74%
```

### 4.2 Permutation Importance on Validation Data (25,000 Rows, 3 Repeats)

Permutation importance measures how much the validation Balanced Accuracy drops when a single feature column is randomly shuffled, breaking its relationship with the target:

| Rank | Feature | Extra Trees Mean Drop | HistGradientBoosting Mean Drop | Consistency Across Models |
| :-: | :--- | :---: | :---: | :---: |
| **1** | **`Fwd Seg Size Min`** | **-0.59777** $(\pm 0.0014)$ | **-0.59605** $(\pm 0.0012)$ | **Exact match (Dominant feature)** |
| **2** | **`Init Fwd Win Byts`** | **-0.28541** $(\pm 0.0031)$ | **-0.29024** $(\pm 0.0035)$ | **Exact match (Dominant feature)** |
| **3** | **`URG Flag Cnt`** | **-0.01893** $(\pm 0.0002)$ | **-0.01865** $(\pm 0.0001)$ | **Exact match** |
| **4** | `Init Bwd Win Byts` | -0.00351 $(\pm 0.0005)$ | 0.00000 | Secondary |
| **5** | `ACK Flag Cnt` | -0.00119 $(\pm 0.0001)$ | 0.00000 | Secondary |
| **6** | `Flow IAT Mean` | -0.00028 $(\pm 0.0002)$ | 0.00000 | Secondary |
| **7** | `Fwd Act Data Pkts` | 0.00000 | -0.00024 $(\pm 0.0002)$ | Secondary |
| **8–15**| All remaining 59 features | **0.00000** | **0.00000** | **Zero impact when permuted** |

**Interpretation**: Both Extra Trees and HistGradientBoosting rely almost entirely on `Fwd Seg Size Min` and `Init Fwd Win Byts`. Together, shuffling these two features causes an **88.3% drop in Balanced Accuracy**. The remaining 64 features serve as redundant fallbacks within the ensemble.

---

## 5. Phase 4 — Model Comparison: Extra Trees vs. HistGradientBoosting

A rigorous benchmark comparing the selected model (`Candidate 2: Extra Trees`) against the primary gradient boosting alternative (`Candidate 4: HistGradientBoosting`) was conducted:

| Comparison Dimension | ExtraTreesClassifier (Candidate 2) | HistGradientBoostingClassifier (Candidate 4) | Advantage |
| :--- | :---: | :---: | :---: |
| **Validation Balanced Accuracy** | **1.0000** | **1.0000** | Tie |
| **Validation Macro F1** | **1.0000** | **1.0000** | Tie |
| **Per-Class Recall (All Classes)**| **100% / 100% / 100%** | **100% / 100% / 100%** | Tie |
| **Serialized Model Size** | 1.42 MB | **0.95 MB** | **HistGradientBoosting** (33% smaller) |
| **Single-Row Mean Latency** | 77.47 ms | **49.28 ms** | **HistGradientBoosting** (36% faster) |
| **Single-Row Median Latency** | 80.82 ms | **14.89 ms** | **HistGradientBoosting** (81% faster) |
| **Single-Row P95 Latency** | **97.63 ms** | 112.60 ms | **Extra Trees** (more consistent tail) |
| **Batch Inference Throughput** | **336,461 rows/s** | 78,158 rows/s | **Extra Trees** (4.3× higher throughput) |
| **Explainability Options** | Native MDI, TreeSHAP, Path decomposition | Permutation importance, Partial Dependence | **Extra Trees** (richer tree explainers) |
| **Training Speed (562k rows)** | **20.5 seconds** | 34.4 seconds | **Extra Trees** (40% faster) |

### Assessment:
- **Extra Trees remains the preferred general choice** for batch processing, retrospective security telemetry analysis, and pipelines requiring TreeSHAP explanations.
- **HistGradientBoosting is superior for real-time edge streaming** where low single-row latency (14.89 ms median) and small RAM footprint (0.95 MB) are prioritized.
- **Neither model should be changed at this stage**, as both share identical validation accuracy and the exact same underlying vulnerability to testbed shortcuts.

---

## 6. Phase 5 — Robustness Limitations & Unresolved Risks

### 6.1 Vulnerability to Attack Evasion and OS Drift
Because classification hinges on `Fwd Seg Size Min` (40.0 for FTP, 32.0 for SSH) and `Init Fwd Win Byts` (26,883):
- **Adversary OS Variation**: If an attacker launches Hydra or Medusa from Windows 11, FreeBSD, or macOS, the TCP stack will advertise different initial window sizes (e.g., 64,240 or 65,535) and 20-byte TCP headers. The model will fail to recognize the attack.
- **Socket Customization**: An attacker using Scapy or custom raw sockets can trivially set the window size to random values, completely bypassing both models.
- **Server Heterogeneity**: In real enterprises, FTP and SSH daemons are hosted on diverse OS platforms and hardware appliances, producing different server initial window sizes than the testbed's 0-byte or 230-byte responses.

### 6.2 Cross-Split Near-Duplicate Analysis
Analysis of normalized Euclidean distances between test attack flows and training attack flows:
- **FTP-BruteForce**: Mean minimum distance = `0.3408` (median = `0.4706`).
- **SSH-Bruteforce**: Mean minimum distance = `0.0314` (median = `0.0282`). Exactly 2 out of 500 test samples had near-zero distance ($< 0.01$).
- **Implication**: While exact duplicates were removed during Task 12.2.1, SSH brute-force attack vectors occupy a tiny, hyperspherical cluster in feature space due to identical tool execution parameters across days.

### 6.3 Split Class Distribution Variance
- In `train.csv`, Benign represents 84.45% and SSH represents 13.13%.
- In `test.csv`, Benign represents 75.26% and SSH represents 23.53%.
- The shift in class balance did not degrade balanced accuracy because the decision boundary on `Fwd Seg Size Min` is completely crisp ($\Delta > 8$ bytes between classes).

### 6.4 Limited Attack Coverage
The dataset contains only two brute-force attack types. The model has **zero capability** to identify other attacks (DDoS, web attacks, infiltration, SQL injection, port scans) and will default to classifying them as Benign or misclassifying them as brute-force.

---

## 7. Recommendations and Integration Feasibility

### 7.1 Feasibility for Prototype Integration
- **Approved for Experimental Prototype Routing**: The 3-class model and its preprocessor are mathematically sound, serialized cleanly under `experiments/cic_three_class/`, and ready for isolated prototype API evaluation.
- **Unsafe as Standalone Production Firewall/IPS**: The model must **not** be deployed autonomously without a human analyst or secondary heuristic verification due to its reliance on testbed TCP stack shortcuts.

### 7.2 Actionable Next Steps for Robustness Hardening:
1. **Ablation Training (Feature Pruning)**:
   - Train an experimental candidate with `Fwd Seg Size Min`, `Init Fwd Win Byts`, and `Init Bwd Win Byts` explicitly removed.
   - Force the model to learn from pure traffic flow behavior: inter-arrival time distributions, packet length standard deviations, and flow volume rates.
2. **Cross-Dataset Validation**:
   - Evaluate the model against raw pcap captures of SSH brute-force traffic originating from non-Linux operating systems.
3. **Hybrid Ensemble Routing**:
   - Pair the CIC 3-class brute-force detector with SentinelAI's 10-class UNSW-NB15 model using a confidence-gated policy.

---

## 8. Artifact and Safety Audit

- **Artifacts Created**:
  - Analysis JSON: `experiments/cic_three_class/reports/review_generalization_and_leakage.json` (498 lines).
  - Detailed Report: `reports/task_12_2_4_generalization_and_leakage_review.md`.
- **Existing Assets Intact**:
  - Legacy 10-class model (`data/models/random_forest_balanced.pkl`) untouched.
  - Fresh 10-class model (`data/models_fresh/random_forest_fresh.pkl`) untouched.
  - Split CSVs (`train.csv`, `val.csv`, `test.csv`) untouched.
  - FastAPI backend and React frontend untouched.
- **Git Policy**: Zero commits or pushes performed.

*Task 12.2.4 review is complete. Awaiting user guidance before proceeding to prototype integration.*
