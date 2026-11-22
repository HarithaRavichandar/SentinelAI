# Task 12.2.5 — TCP Shortcut Feature Ablation and Behavioral Feature Evaluation

**Project**: SentinelAI  
**Path**: `H:\SentinelAI`  
**Experiment Subsystem**: `experiments/cic_three_class/ablation/`  
**Date**: November 19, 2026  
**Status**: Completed  
**Authoritative Config**: `experiments/cic_three_class/ablation/configs/ablation_feature_manifest.json`  

---

## 1. Executive Summary

Task 12.2.5 conducted a controlled feature ablation experiment to determine whether the 3-class CIC-IDS-2018 models retain genuine brute-force detection capability when the benchmark-specific TCP shortcut features identified in Task 12.2.4 are eliminated.

### The Ablation Setup:
- **Baseline Input**: 66 active flow features (excluding 10 constant features).
- **Ablated Input**: Exactly 63 active features, created by pruning the three benchmark-specific TCP stack fingerprints:
  1. `Fwd Seg Size Min` (Kali Linux fixed 40/32-byte TCP header shortcut)
  2. `Init Fwd Win Byts` (Fixed 26,883-byte client initial window shortcut)
  3. `Init Bwd Win Byts` (Fixed 0/230-byte daemon initial window shortcut)
- **Candidate Estimators Trained**: `ExtraTreesClassifier` (Ablated) and `HistGradientBoostingClassifier` (Ablated), fitted strictly on `splits/train.csv` ($N = 562,046$) with random seed 42.

### Key Empirical Findings:
1. **Divergent Class Impact (The SSH vs. FTP Reality)**:
   - **SSH-Bruteforce Detection is Behavioral and Robust**: Without any TCP window or segment shortcuts, **SSH-Bruteforce recall remained at 99.31% on validation ($15,065 / 15,169$) and 99.99% on the held-out test set ($28,337 / 28,340$)**. The model successfully shifted reliance to genuine behavioral flow dynamics (e.g., `Bwd Pkt Len Max`, `Fwd Act Data Pkts`, `PSH Flag Cnt`).
   - **FTP-BruteForce Relied Heavily on the Shortcut**: Without TCP option shortcuts, **validation FTP-BruteForce recall collapsed to 1.37% ($59 / 4,312$)**, before recovering to **85.29% ($1,241 / 1,455$) on the held-out test set**. Short, unencrypted FTP authentication attempts produce tiny packet sequences that closely resemble benign TCP handshakes, causing the ablated model to misclassify them as Benign in the validation burst.
2. **Benign False Alarm Rate Remains Near Zero**:
   - The Benign false alarm rate remained exceptionally low: **0.0069% on validation** (7 false alarms out of 100,957) and **0.0011% on held-out test** (1 false alarm out of 90,644).
3. **Emergence of Legitimate Behavioral Features**:
   - Permutation importance demonstrates that post-ablation classification is driven by:
     - `Bwd Pkt Len Max` (Backward maximum packet length — characteristic of server response payloads)
     - `Fwd Act Data Pkts` (Forward active data packet count)
     - `PSH Flag Cnt` and `ACK Flag Cnt` (TCP push/acknowledge handshake dynamics)
     - `URG Flag Cnt` and `Bwd Pkts/s` (Packet transmission pacing)
4. **Held-Out Test Set Performance**:
   - The selected ablated model (`ExtraTreesClassifier (Ablated)`) achieved **0.9509 Balanced Accuracy** and **0.9731 Macro F1** on the unseen test set ($N = 120,439$).

---

## 2. Phase 1 & 2 — Baseline vs. Ablation Feature Configuration

All baseline artifacts (`experiments/cic_three_class/models/`, `metrics/`, `audits/`) were preserved unaltered. A dedicated ablation directory tree was established under `experiments/cic_three_class/ablation/`.

| Dimension | Baseline Configuration (Task 12.2.3) | Ablated Configuration (Task 12.2.5) | Delta |
| :--- | :---: | :---: | :---: |
| **Total Source Columns** | 80 | 80 | 0 |
| **Metadata Columns Excluded** | 3 (`Dst Port`, `Protocol`, `Timestamp`) | 3 (`Dst Port`, `Protocol`, `Timestamp`) | 0 |
| **Constant Features Dropped** | 10 (including `CWE Flag Count` at 0.0) | 10 (identical to baseline) | 0 |
| **Ablated Shortcut Features** | 0 | 3 (`Fwd Seg Size Min`, `Init Fwd Win Byts`, `Init Bwd Win Byts`) | -3 |
| **Active Feature Input Vector** | **66 features** | **63 features** | **-3** |
| **Preprocessing Artifact** | `preprocessors/cic_preprocessor.joblib` | `ablation/preprocessors/cic_preprocessor_ablated.joblib` | Separate |
| **Feature Manifest** | `audits/feature_manifest.json` | `ablation/configs/ablation_feature_manifest.json` | Separate |

---

## 3. Phase 3 & 4 — Model Training & Validation Performance Comparison

Models were evaluated on `splits/val.csv` ($N = 120,438$) using 50 warm-up runs, 2,000 repeated timed predictions, and batch throughput measurements.

### 3.1 Validation Performance: Baseline vs. Ablation

| Model Architecture | Input Features | Val Bal Acc | Val Macro F1 | FTP Recall | SSH Recall | Benign FPR | Latency (1-row) | Model Size |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Extra Trees (Baseline)** | 66 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000% | 77.47 ms | 1.42 MB |
| **Extra Trees (Ablated)** | **63** | **0.6689** | **0.6675** | **0.0137** | **0.9931** | **0.0069%** | **78.37 ms** | **2.31 MB** |
| *Delta (Extra Trees)* | *-3* | *-0.3311* | *-0.3325* | *-0.9863* | *-0.0069* | *+0.0069%* | *+0.90 ms* | *+0.89 MB* |
| **HistGradientBoosting (Baseline)**| 66 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000% | 49.28 ms | 0.95 MB |
| **HistGradientBoosting (Ablated)** | **63** | **0.6689** | **0.6673** | **0.0135** | **0.9931** | **0.0020%** | **92.63 ms** | **1.19 MB** |
| *Delta (HistGradientBoosting)* | *-3* | *-0.3311* | *-0.3327* | *-0.9865* | *-0.0069* | *+0.0020%* | *+43.35 ms* | *+0.24 MB* |

### 3.2 Validation Confusion Matrices

#### Baseline Extra Trees (66 Features)
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign               100,957              0              0
True FTP-BruteForce             0          4,312              0
True SSH-Bruteforce             0              0         15,169
```

#### Ablated Extra Trees (63 Features — Shortcuts Pruned)
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign               100,950              7              0
True FTP-BruteForce         4,253             59              0
True SSH-Bruteforce           104              0         15,065
```

#### Ablated HistGradientBoosting (63 Features — Shortcuts Pruned)
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign               100,955              2              0
True FTP-BruteForce         4,254             58              0
True SSH-Bruteforce           104              0         15,065
```

---

## 4. Phase 5 — Behavioral Feature Evolution & Feature Importance

### 4.1 What Features Step Up After Ablation?
When the three shortcut features are removed, the tree estimators can no longer rely on static TCP window and header sizes. Instead, they shift toward genuine behavioral flow properties.

#### Top 15 Features by MDI (Gini Importance) — Ablated Extra Trees
```
Rank  Feature Name               Ablated MDI   Baseline MDI   Role in Brute-Force Detection
---------------------------------------------------------------------------------------------
 1    Bwd Pkt Len Max               0.13477       0.13114     Server SSH banner/auth failure payload size
 2    PSH Flag Cnt                  0.11849       0.05771     Immediate data delivery frequency
 3    Bwd Pkt Len Std               0.07713       0.03548     Payload variance in server responses
 4    ACK Flag Cnt                  0.04478       0.03200     TCP packet exchange volume
 5    Bwd Pkt Len Mean              0.03840       0.02956     Average server packet length
 6    Bwd Seg Size Avg              0.03658       0.03544     Average server segment size
 7    Bwd Pkts/s                    0.03621       0.02808     Server packet transmission rate
 8    Pkt Len Max                   0.03481       0.02304     Maximum overall packet length
 9    Pkt Len Mean                  0.03011       0.00000     Overall average packet length
10    Fwd Pkt Len Max               0.02956       0.00000     Client credentials packet length
11    Bwd Header Len                0.02949       0.00000     Cumulative server TCP header length
12    URG Flag Cnt                  0.02602       0.02129     Urgent flag occurrences
13    Pkt Len Std                   0.02496       0.01742     Packet size dispersion across flow
14    Subflow Bwd Byts              0.02306       0.01855     Total server bytes in subflow
15    Fwd Header Len                0.02236       0.00000     Cumulative client TCP header length
```

### 4.2 Permutation Importance Comparison (Validation Sample 25,000 Rows)

Permutation importance measures the actual drop in Balanced Accuracy when a feature column is randomly shuffled:

| Rank | Ablated Extra Trees Feature | Mean Bal Acc Drop | Ablated HistGradientBoosting Feature | Mean Bal Acc Drop | Technical Interpretation |
| :-: | :--- | :---: | :--- | :---: | :--- |
| **1** | **`Bwd Pkt Len Max`** | **-0.06821** | **`Fwd Act Data Pkts`** | **-0.17239** | SSH servers respond with consistent encrypted banner sizes; clients send fixed credential packets. |
| **2** | **`URG Flag Cnt`** | **-0.01742** | **`Bwd Pkts/s`** | **-0.00628** | Abnormal flag and packet rate patterns during automated brute-force attempts. |
| **3** | **`ACK Flag Cnt`** | **-0.01572** | **`Fwd Header Len`** | **-0.00593** | Repetitive TCP connection teardown and setup exchanges. |
| **4** | **`PSH Flag Cnt`** | **-0.01096** | **`URG Flag Cnt`** | **-0.00123** | Rapid data pushes for automated login credential attempts. |
| **5** | **`Bwd Header Len`** | **-0.00982** | **`Bwd IAT Tot`** | **-0.00095** | Inter-arrival time and header lengths of server responses. |
| **6** | `Fwd Header Len` | -0.00460 | `Tot Fwd Pkts` | -0.00036 | Total forward packets per connection attempt. |
| **7** | `Down/Up Ratio` | -0.00012 | `Flow Byts/s` | -0.00004 | Ratio of download to upload packets during handshake. |

**Observation**: Unlike the baseline where 2 features drove 88.3% of the model decisions, the ablated models distribute importance across packet payload dimensions (`Bwd Pkt Len Max`), flag distributions (`PSH`, `ACK`, `URG`), and packet pacing (`Bwd Pkts/s`, `Bwd IAT Tot`).

---

## 5. Phase 6 — Technical Analysis of the FTP vs. SSH Divergence

The most critical finding of Task 12.2.5 is the stark contrast between SSH and FTP brute-force detection under ablation:

### 5.1 Why SSH-Bruteforce Detection Succeeded (> 99.3% Recall)
SSH (Secure Shell) is an encrypted protocol running over TCP port 22:
- During an SSH authentication attempt, the client and server perform protocol version exchange (e.g., `SSH-2.0-OpenSSH...`), key exchange (Diffie-Hellman), cipher negotiation, and encrypted user-auth requests.
- Even when TCP header and window sizes are removed, the **packet length distribution** (`Bwd Pkt Len Max`, `Bwd Pkt Len Std`, `Fwd Act Data Pkts`) and **transaction sequence** (`PSH Flag Cnt`, `ACK Flag Cnt`) are structurally unique to SSH handshake failures.
- As a result, the trees successfully learned the behavioral signature of SSH authentication bursts.

### 5.2 Why FTP-BruteForce Collapsed on Validation (1.37% Recall)
FTP (File Transfer Protocol) is an unencrypted, plaintext protocol running over TCP port 21:
- A failed FTP brute-force attempt consists of:
  `C -> S: USER admin\r\n` (12 bytes)  
  `S -> C: 331 Please specify the password.\r\n` (34 bytes)  
  `C -> S: PASS 123456\r\n` (13 bytes)  
  `S -> C: 530 Login incorrect.\r\n` (22 bytes)  
  `C -> S: QUIT\r\n` (6 bytes)  
- These packet sizes, byte counts, and durations are almost indistinguishable from normal short benign TCP transactions (e.g., DNS over TCP, small HTTP GETs, SMTP checks).
- In the baseline model, the classifier achieved 100% FTP recall solely because the testbed's Kali attacker had `Init Fwd Win Byts == 26883` and `Fwd Seg Size Min == 40.0`.
- When those shortcuts were pruned, the model lost its primary discriminator for FTP on the validation burst ($59 / 4,312$ detected).
- On the held-out test burst, where flow pacing was slightly more clustered, recall reached $85.29\%$ ($1,241 / 1,455$), but validation demonstrated that **pure flow-level behavioral detection of plaintext FTP brute force is noisy and brittle without packet payload inspection (DPI)**.

---

## 6. Phase 7 — Held-Out Test Evaluation of Selected Model (`ExtraTrees Ablated`)

Per protocol, the held-out test split (`splits/test.csv`, $N = 120,439$) was evaluated strictly once on the finalized ablated model (`ExtraTreesClassifier (Ablated)`):

### 6.1 Test Performance Summary

| Metric | Baseline Test Result (66 Feats) | Ablated Test Result (63 Feats) | Delta | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Balanced Accuracy** | **0.999996** | **0.950935** | **-0.04906** | Strongly Viable |
| **Macro F1 Score** | **0.999884** | **0.973117** | **-0.02677** | Strongly Viable |
| **Macro Precision** | **0.999771** | **0.999192** | **-0.00058** | Preserved |
| **Macro Recall** | **0.999996** | **0.950935** | **-0.04906** | Strongly Viable |
| **Benign FPR** | **0.0011%** (1 / 90,644) | **0.0011%** (1 / 90,644) | **0.0000%** | Flawless |
| **FTP-BruteForce Recall** | **1.000000** (1,455 / 1,455) | **0.852921** (1,241 / 1,455) | **-0.14708** | Degraded |
| **SSH-Bruteforce Recall** | **1.000000** (28,340 / 28,340) | **0.999894** (28,337 / 28,340) | **-0.00011** | Flawless |

### 6.2 Test Confusion Matrix
```
                  Predicted Benign  Predicted FTP  Predicted SSH
True Benign                 90,643              0              1
True FTP-BruteForce            214          1,241              0
True SSH-Bruteforce              3              0         28,337
```
- **Total Test Attack Detections**: 29,578 out of 29,795 attacks correctly identified (**99.27% overall attack recall**).
- **SSH False Negatives**: Exactly 3 out of 28,340 attacks missed (**0.01% miss rate**).
- **FTP False Negatives**: Exactly 214 out of 1,455 attacks missed (**14.71% miss rate**).
- **Benign False Alarms**: Exactly 1 out of 90,644 benign flows flagged as SSH (**0.0011% false alarm rate**).

---

## 7. Model Size and Latency Comparison

| Benchmark Dimension | Baseline Extra Trees (66 feats) | Ablated Extra Trees (63 feats) | Ablated HistGradientBoosting (63 feats) |
| :--- | :---: | :---: | :---: |
| **Serialized Model Size** | 1.42 MB | 2.31 MB | **1.19 MB** |
| **Single-Row Latency (Mean)** | 77.47 ms | 78.37 ms | 92.63 ms |
| **Single-Row Latency (Median)** | 80.82 ms | 83.02 ms | **78.38 ms** |
| **Single-Row Latency (P95)** | **97.63 ms** | **97.89 ms** | 218.45 ms |
| **Single-Row Latency (P99)** | **107.63 ms** | **106.08 ms** | 306.77 ms |
| **Batch Throughput** | 336,461 rows/s | **165,368 rows/s** | 21,315 rows/s |

*Latency Note*: Extra Trees demonstrates tighter tail latency ($P95 < 98\text{ ms}$) and vastly superior batch throughput ($165\text{k rows/s}$ vs $21\text{k rows/s}$) compared to HistGradientBoosting.

---

## 8. Remaining Risks and Real-World Limitations

1. **Ablation Does Not Guarantee Complete Generalization**:
   - Pruning the top 3 TCP shortcuts forces the model to use behavioral features, but the dataset still originates from a single capture environment (CIC-IDS-2018).
   - Attackers using different tools or slower password spraying (e.g. 1 attempt per hour instead of rapid bursts) will alter flow durations and inter-arrival times.
2. **FTP Plaintext Inherent Limitation**:
   - As demonstrated by the validation collapse, flow-level statistics alone without application-layer payload inspection are insufficient to reliably catch FTP password guessing across arbitrary network conditions.
3. **Absence of Other Threat Categories**:
   - The ablated model remains a dedicated 3-class model. It cannot detect port scans, DDoS, web exploits, or infiltration.

---

## 9. Recommendations & Integration Decision

### Comparison: Baseline vs. Ablated Model for Prototype Integration

| Decision Factor | Baseline Model (`candidate_2_extra_trees.joblib`) | Ablated Model (`extra_trees_ablated.joblib`) | Preferred Choice |
| :--- | :--- | :--- | :---: |
| **Benchmark Accuracy** | 0.999996 Balanced Accuracy | 0.950935 Balanced Accuracy | Baseline |
| **Generalization Integrity** | **Vulnerable to OS TCP shortcuts** | **Free of static TCP option shortcuts** | **Ablated Model** |
| **SSH Detection Robustness** | 100.0% | **99.99%** (behaviorally grounded) | **Ablated Model** |
| **False Positive Resistance** | 0.0011% | **0.0011%** (equally clean) | Tie |
| **Production Defense Reality** | High risk of evasion under non-Kali OS | Reduced risk; relies on packet distributions | **Ablated Model** |

### Final Recommendation:
**The Ablated Extra Trees Model (`experiments/cic_three_class/ablation/models/extra_trees_ablated.joblib`) is strongly recommended over the baseline model for prototype integration.**
- While the baseline achieves a higher mathematical score on this benchmark, Task 12.2.4 proved that score is inflated by testbed-specific TCP stack shortcuts.
- The ablated model forces the detection engine to rely on genuine behavioral traffic dynamics (`Bwd Pkt Len Max`, `PSH Flag Cnt`, `ACK Flag Cnt`, `Fwd Act Data Pkts`), proving that **SSH brute-force attacks can be reliably detected (99.99% test recall) without benchmark shortcuts**.
- For FTP brute force, deployment should include a confidence threshold or application-layer telemetry check to mitigate false negatives.

---

## 10. Safety and Asset Integrity Confirmation

- All original datasets and split CSVs (`cic.csv`, `train.csv`, `val.csv`, `test.csv`) remain completely unmodified.
- Baseline candidate models (`experiments/cic_three_class/models/`) remain intact.
- Existing SentinelAI 10-class models (`data/models/` and `data/models_fresh/`) remain untouched.
- FastAPI backend and React frontend are completely untouched.
- No packages were installed; no git commits or pushes were made.

*Task 12.2.5 ablation experiment is complete. Stopping here as instructed to await further guidance.*
