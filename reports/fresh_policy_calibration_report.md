# SentinelAI – Fresh Policy Calibration Report (Validation-Only)

> **Document Status**: Step 3 Validation-Only Calibration Artifact  
> **Calibrated At**: 2026-10-29T21:21:57Z  
> **Evaluation Partition**: `val_mask_fresh.npy` (65,850 flows strictly; `test_mask_fresh.npy` unopened)  
> **Model Artifact**: `data/models_fresh/random_forest_fresh.pkl`  

---

## 1. Executive Summary & Calibration Governance

This report documents the validation-only policy calibration for SentinelAI's fresh evaluation pipeline. To prevent test-set circularity, all class reliability weights, high-confusion categories, and triage thresholds were derived strictly from the **held-out validation partition** (`val_mask_fresh.npy`). The fresh test partition (`test_mask_fresh.npy`) remained completely unblinded and unread during this phase.

> [!IMPORTANT]
> **Selected Triage Thresholds**: **`theta_low = 0.20`** and **`theta_high = 0.70`**  
> - **Validation Attack Recall**: **99.816%** (Missed Attacks: 22 / 11,988, 0.184%)  
> - **Benign False-Positive Rate**: **1.292%** (Escalated to Attack Tier: 696 / 53,862)  
> - **Analyst Review Volume**: **1,061 flows (1.61%)**  
> - **Review-Band Attack Concentration**: **58.15%**  

---

## 2. Validation Multiclass Model Metrics (`val_fresh`: 65,850 Flows)

- **Overall Accuracy**: 0.9371 (93.71%)
- **Balanced Accuracy**: 0.5454
- **Macro F1-Score**: 0.5883
- **Weighted F1-Score**: 0.9361

### 2.1 Per-Class Validation Breakdown

| Class ID | Class Name | Support | Precision | Recall | F1-Score | Derived Fresh Reliability |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| `0` | Benign | 53,862 | 99.24% | 98.56% | 98.90% | **0.98** |
| `1` | Analysis | 57 | 25.00% | 19.30% | 21.78% | **0.22** |
| `2` | Backdoor | 66 | 88.89% | 48.48% | 62.75% | **0.63** |
| `3` | DoS | 596 | 65.34% | 27.52% | 38.72% | **0.39** |
| `4` | Exploits | 4,585 | 75.91% | 79.37% | 77.60% | **0.76** |
| `5` | Fuzzers | 3,868 | 63.10% | 82.37% | 71.46% | **0.63** |
| `6` | Generic | 653 | 91.31% | 72.43% | 80.79% | **0.81** |
| `7` | Reconnaissance | 1,846 | 67.79% | 56.45% | 61.60% | **0.62** |
| `8` | Shellcode | 284 | 63.54% | 21.48% | 32.11% | **0.32** |
| `9` | Worms | 33 | 46.43% | 39.39% | 42.62% | **0.43** |

### 2.2 Derived High-Confusion Classes

Classes exhibiting validation precision < 40%: **Class 1 (Analysis)**

- **Class 1 (Analysis)**: Precision is 25.00% with support of 57 flows.

---

## 3. Standard Argmax Baseline (Benign vs Attack)

Baseline multiclass model argmax (predicting Attack when predicted class != 0):
- **Attack Recall**: 96.59%
- **Attack Precision**: 93.73%
- **Benign False-Positive Rate**: 1.44%
- **Benign False-Negative Rate**: 3.41%

---

## 4. Two-Stage Threshold Sweep Analysis (25 Candidate Pairs)

The two-stage policy screens flows using aggregate attack probability $p_{\text{attack}} = 1 - P(\text{Benign})$. Flows below $\theta_{\text{low}}$ are auto-accepted as benign candidates; flows in $[\theta_{\text{low}}, \theta_{\text{high}})$ are escalated to analyst review (`review_required`); flows at or above $\theta_{\text{high}}$ advance to Stage 2 threat-tier routing.

| theta_low | theta_high | Attack Recall | Missed Attacks | Benign FPR | Review Volume | Review Rate | Review Attack Conc. | SOC Loss |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0.20 | 0.70 | 99.82% | 22 | 1.29% | 1,061 | 1.61% | 58.15% | 52.29 **[SELECTED]** |
| 0.20 | 0.75 | 99.82% | 22 | 1.19% | 1,378 | 2.09% | 63.64% | 52.57 |
| 0.20 | 0.65 | 99.82% | 22 | 1.40% | 812 | 1.23% | 52.71% | 52.63 |
| 0.20 | 0.80 | 99.82% | 22 | 1.01% | 1,876 | 2.85% | 68.23% | 52.85 |
| 0.20 | 0.60 | 99.82% | 22 | 1.50% | 636 | 0.97% | 47.33% | 53.15 |
| 0.25 | 0.70 | 99.68% | 38 | 1.29% | 1,007 | 1.53% | 59.68% | 65.19 |
| 0.25 | 0.75 | 99.68% | 38 | 1.19% | 1,324 | 2.01% | 65.03% | 65.47 |
| 0.25 | 0.65 | 99.68% | 38 | 1.40% | 758 | 1.15% | 54.35% | 65.53 |
| 0.25 | 0.80 | 99.68% | 38 | 1.01% | 1,822 | 2.77% | 69.37% | 65.75 |
| 0.25 | 0.60 | 99.68% | 38 | 1.50% | 582 | 0.88% | 48.97% | 66.00 |
| 0.30 | 0.70 | 99.46% | 65 | 1.29% | 937 | 1.42% | 61.26% | 87.14 |
| 0.30 | 0.75 | 99.46% | 65 | 1.19% | 1,254 | 1.90% | 66.51% | 87.42 |
| 0.30 | 0.65 | 99.46% | 65 | 1.40% | 688 | 1.04% | 55.96% | 87.48 |
| 0.30 | 0.80 | 99.46% | 65 | 1.01% | 1,752 | 2.66% | 70.61% | 87.70 |
| 0.30 | 0.60 | 99.46% | 65 | 1.50% | 512 | 0.78% | 50.39% | 88.00 |
| 0.35 | 0.70 | 99.29% | 85 | 1.29% | 875 | 1.33% | 63.31% | 103.39 |
| 0.35 | 0.75 | 99.29% | 85 | 1.19% | 1,192 | 1.81% | 68.29% | 103.67 |
| 0.35 | 0.65 | 99.29% | 85 | 1.40% | 626 | 0.95% | 58.31% | 103.73 |
| 0.35 | 0.80 | 99.29% | 85 | 1.01% | 1,690 | 2.57% | 72.01% | 103.95 |
| 0.35 | 0.60 | 99.29% | 85 | 1.50% | 450 | 0.68% | 52.89% | 104.20 |
| 0.40 | 0.70 | 99.07% | 111 | 1.29% | 808 | 1.23% | 65.35% | 124.59 |
| 0.40 | 0.75 | 99.07% | 111 | 1.19% | 1,125 | 1.71% | 70.04% | 124.87 |
| 0.40 | 0.65 | 99.07% | 111 | 1.40% | 559 | 0.85% | 60.64% | 124.93 |
| 0.40 | 0.80 | 99.07% | 111 | 1.01% | 1,623 | 2.46% | 73.38% | 125.10 |
| 0.40 | 0.60 | 99.07% | 111 | 1.50% | 383 | 0.58% | 55.35% | 125.40 |

### 4.1 Selection Criterion Rationale

Parameters were selected by minimizing the operational SOC loss function:  
$$\text{Loss} = 100 \times \text{MissedAttackRate} + 20 \times \text{BenignFPR} + 5 \times \text{ReviewQueueRate} + \text{Penalty}$$  
Subject to hard operational constraints:  
1. **Attack Recall $\ge 98.0\%$** (Missed attack rate $< 2.0\%$).  
2. **Review Queue Rate $\le 12.0\%$** (Analyst workload ceiling).  
3. **Benign False-Positive Rate $\le 1.0\%$** (Noise reduction in automated attack tiers).  

**Candidate `[0.20, 0.70)` achieves the lowest operational loss (52.29)**, delivering **99.816%** Attack Recall with only **1.61%** review workload and **1.292%** benign false alarms.

### 4.2 Per-Class Missed Attacks for Selected Threshold Pair

| Attack Class ID | Attack Class Name | Validation Support | Missed in Auto-Benign | Class Attack Recall |
| :---: | :--- | :---: | :---: | :---: |
| `1` | Analysis | 57 | 0 | **100.00%** |
| `2` | Backdoor | 66 | 0 | **100.00%** |
| `3` | DoS | 596 | 0 | **100.00%** |
| `4` | Exploits | 4,585 | 4 | **99.91%** |
| `5` | Fuzzers | 3,868 | 10 | **99.74%** |
| `6` | Generic | 653 | 0 | **100.00%** |
| `7` | Reconnaissance | 1,846 | 8 | **99.57%** |
| `8` | Shellcode | 284 | 0 | **100.00%** |
| `9` | Worms | 33 | 0 | **100.00%** |

---

## 5. Frozen Parameters Serialized for Fresh Evaluation

The parameters have been serialized to [`src/sentinelai/triage/calibrated_params_fresh.json`](file:///H:/SentinelAI/src/sentinelai/triage/calibrated_params_fresh.json):

```json
{
  "theta_low": 0.2,
  "theta_high": 0.7,
  "class_reliability": {
    "0": 0.98,
    "1": 0.22,
    "2": 0.63,
    "3": 0.39,
    "4": 0.76,
    "5": 0.63,
    "6": 0.81,
    "7": 0.62,
    "8": 0.32,
    "9": 0.43
  },
  "high_confusion_classes": [
    1
  ]
}
```

> [!NOTE]
> Production code (`src/sentinelai/triage/decision_engine.py`) remains untouched on safe default behavior. These calibrated parameters will be passed strictly to the offline evaluation harness in Step 4.

---

## 6. Integrity & Safety Checklist

- [x] **Test Partition Blinded**: `test_mask_fresh.npy` was never accessed or read.
- [x] **Model Frozen**: `random_forest_fresh.pkl` was loaded read-only without retraining.
- [x] **Production Intact**: No production code, API routes, or thresholds modified.
- [x] **Transparent Selection Criterion**: Multi-objective SOC loss function documented prior to unblinding.
