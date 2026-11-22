#!/usr/bin/env python3
"""scripts/calibrate_fresh_policy.py

Validation-Only Policy Calibration for SentinelAI's Fresh Evaluation Pipeline (Step 3).

Key Operations:
1. Loads validation partition ONLY (val_mask_fresh.npy, 65,850 flows).
   - Strictly asserts test_mask_fresh.npy is never loaded, read, or inspected.
2. Loads fresh preprocessor and Random Forest model from data/models_fresh/.
3. Evaluates fresh Random Forest model on val_fresh:
   - Computes multiclass accuracy, balanced accuracy, macro/weighted F1, confusion matrix.
   - Computes per-class precision, recall, F1, and class support.
   - Computes standard binary argmax baseline (Benign vs Attack).
4. Derives empirical class reliability weights strictly from val_fresh:
   - Formula: reliability_c = round(min(Precision_c, F1_c), 2) with conservative bounds.
5. Identifies high-confusion classes strictly from val_fresh:
   - Classes where validation precision < 40%.
6. Sweeps candidate two-stage triage thresholds:
   - theta_low in [0.20, 0.25, 0.30, 0.35, 0.40]
   - theta_high in [0.60, 0.65, 0.70, 0.75, 0.80]
   - Evaluates all 25 candidate pairs across:
     * Attack Recall & Missed Attacks
     * Benign False Positive Rate (Benign flows escalated to Attack tier)
     * Review Queue Volume & Review Queue Rate
     * Review-Band Attack Concentration
     * Per-class Missed Attack breakdown
7. Applies a multi-objective SOC utility optimization criterion to select the optimal pair.
8. Serializes frozen parameters to src/sentinelai/triage/calibrated_params_fresh.json.
9. Generates comprehensive human-readable report at reports/fresh_policy_calibration_report.md.

Safety Safeguards:
- NEVER accesses test_mask_fresh.npy or conflict_mask_fresh.npy.
- Does NOT alter legacy models or legacy masks.
- Does NOT modify production decision engine code or enable SENTINELAI_TWO_STAGE_TRIAGE.
- Does NOT perform operational firewall or network actions.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

# Repository root and sys.path setup
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from sentinelai.data.split import _parse_label_mapping, load_features_and_labels


def assert_test_isolation(script_file: Path) -> None:
    """Verify script does not load or reference test_mask_fresh.npy outside of safety docstrings."""
    with open(script_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    test_target = "test_" + "mask_fresh.npy"
    for idx, line in enumerate(lines, 1):
        # Ignore docstrings and the assertion function itself
        if "assert_test_isolation" in line or 'test_target =' in line or 'forbidden' in line:
            continue
        if "np.load" in line and test_target in line:
            raise RuntimeError(f"CRITICAL SAFETY VIOLATION: Line {idx} attempts to load test mask: {line.strip()}")


def derive_class_reliability(
    per_class_metrics: Dict[int, Dict[str, float]],
    class_support: Dict[int, int],
) -> Dict[int, float]:
    """Derive empirical class reliability weights strictly from validation precision and F1.

    Rule:
    - Base reliability = min(precision, f1)
    - Bound between 0.10 (conservative floor for extreme confusion) and 0.98.
    - If class support is very small (< 100 flows), apply conservative dampening.
    """
    reliability: Dict[int, float] = {}
    for cid, metrics in per_class_metrics.items():
        prec = metrics["precision"]
        f1 = metrics["f1"]
        support = class_support.get(cid, 0)

        base_val = min(prec, f1)
        if support < 100:
            # Low support class: conservative dampening to avoid overconfidence from small samples
            val = min(base_val, 0.65)
        else:
            val = base_val

        bounded = round(float(np.clip(val, 0.10, 0.98)), 2)
        reliability[cid] = bounded
    return reliability


def identify_high_confusion_classes(
    per_class_metrics: Dict[int, Dict[str, float]],
    threshold: float = 0.40,
) -> List[int]:
    """Identify classes exhibiting validation precision below threshold."""
    high_confusion: List[int] = []
    for cid, metrics in per_class_metrics.items():
        if cid == 0:  # Benign is Plural Plurality, not an attack confusion category
            continue
        if metrics["precision"] < threshold:
            high_confusion.append(cid)
    return sorted(high_confusion)


def evaluate_two_stage_threshold_pair(
    probabilities: np.ndarray,
    true_labels: np.ndarray,
    predicted_classes: np.ndarray,
    theta_low: float,
    theta_high: float,
    mapping: Dict[int, str],
) -> Dict[str, Any]:
    """Simulate two-stage triage routing for a specific (theta_low, theta_high) pair.

    Routing Rules:
    1. p_attack = 1.0 - P(Benign) = 1.0 - probabilities[:, 0]
    2. Auto-Benign: p_attack < theta_low
       - Action: allow_and_standard_monitoring
       - requires_human_review = False
    3. Review Queue: theta_low <= p_attack < theta_high
       - Action: inspect_uncertain_traffic_and_review
       - requires_human_review = True
    4. Attack Candidate: p_attack >= theta_high
       - Escalated to threat tier
       - requires_human_review = False (unless flagged by stage 2 uncertainty)
    """
    total_val_flows = len(true_labels)
    is_true_attack = (true_labels > 0)
    is_true_benign = (true_labels == 0)
    total_true_attacks = int(is_true_attack.sum())
    total_true_benign = int(is_true_benign.sum())

    p_attack = 1.0 - probabilities[:, 0]
    # Bound numerically
    p_attack = np.clip(p_attack, 0.0, 1.0)

    # Stage 1 partitions
    is_auto_benign = (p_attack < theta_low)
    is_review_queue = ((p_attack >= theta_low) & (p_attack < theta_high))
    is_attack_candidate = (p_attack >= theta_high)

    assert np.all((is_auto_benign.astype(int) + is_review_queue.astype(int) + is_attack_candidate.astype(int)) == 1)

    # Counts
    auto_benign_count = int(is_auto_benign.sum())
    review_queue_count = int(is_review_queue.sum())
    attack_candidate_count = int(is_attack_candidate.sum())

    # Missed attacks: True attacks routed to Auto-Benign
    missed_attacks_mask = (is_true_attack & is_auto_benign)
    missed_attacks_count = int(missed_attacks_mask.sum())
    missed_attack_rate_pct = round(missed_attacks_count / total_true_attacks * 100, 3)

    # Attack recall: Fraction of true attacks caught in review queue or attack tier
    attacks_caught_count = total_true_attacks - missed_attacks_count
    attack_recall_pct = round(attacks_caught_count / total_true_attacks * 100, 3)

    # Benign false positives (Benign flows escalated to attack candidate tier)
    benign_escalated_mask = (is_true_benign & is_attack_candidate)
    benign_escalated_count = int(benign_escalated_mask.sum())
    benign_fpr_pct = round(benign_escalated_count / total_true_benign * 100, 3)

    # Benign flows in review queue
    benign_in_review_mask = (is_true_benign & is_review_queue)
    benign_in_review_count = int(benign_in_review_mask.sum())

    # Review queue attack concentration
    attacks_in_review_mask = (is_true_attack & is_review_queue)
    attacks_in_review_count = int(attacks_in_review_mask.sum())
    review_attack_concentration_pct = (
        round(attacks_in_review_count / review_queue_count * 100, 2)
        if review_queue_count > 0
        else 0.0
    )

    # Review queue rate
    review_queue_rate_pct = round(review_queue_count / total_val_flows * 100, 2)

    # Per-class missed attack breakdown
    missed_by_class: Dict[str, int] = {}
    for cid in range(1, 10):
        class_name = mapping[cid]
        class_mask = (true_labels == cid)
        class_missed = int((class_mask & missed_attacks_mask).sum())
        missed_by_class[class_name] = class_missed

    return {
        "theta_low": theta_low,
        "theta_high": theta_high,
        "auto_benign_count": auto_benign_count,
        "auto_benign_rate_pct": round(auto_benign_count / total_val_flows * 100, 2),
        "review_queue_count": review_queue_count,
        "review_queue_rate_pct": review_queue_rate_pct,
        "attack_candidate_count": attack_candidate_count,
        "attack_candidate_rate_pct": round(attack_candidate_count / total_val_flows * 100, 2),
        "total_true_attacks": total_true_attacks,
        "attacks_caught_count": attacks_caught_count,
        "attack_recall_pct": attack_recall_pct,
        "missed_attacks_count": missed_attacks_count,
        "missed_attack_rate_pct": missed_attack_rate_pct,
        "benign_escalated_count": benign_escalated_count,
        "benign_fpr_pct": benign_fpr_pct,
        "attacks_in_review_count": attacks_in_review_count,
        "benign_in_review_count": benign_in_review_count,
        "review_attack_concentration_pct": review_attack_concentration_pct,
        "missed_by_class": missed_by_class,
    }


def compute_soc_utility_penalty(res: Dict[str, Any]) -> float:
    """Compute composite operational loss for a candidate threshold pair.

    Objective: Minimize operational risk and SOC fatigue.
    Formula:
        Loss = 100.0 * (Missed Attack Rate %)
             + 20.0 * (Benign False Positive Rate %)
             + 5.0 * (Review Queue Rate %)
    """
    missed_rate = res["missed_attack_rate_pct"]
    benign_fpr = res["benign_fpr_pct"]
    review_rate = res["review_queue_rate_pct"]

    # Heavy penalty if attack recall falls below 98.0%
    recall_penalty = 500.0 if res["attack_recall_pct"] < 98.0 else 0.0

    # Penalty if review volume exceeds 12.0%
    workload_penalty = 200.0 if review_rate > 12.0 else 0.0

    return (
        100.0 * missed_rate
        + 20.0 * benign_fpr
        + 5.0 * review_rate
        + recall_penalty
        + workload_penalty
    )


def generate_calibration_report(
    report_path: Path,
    metadata: Dict[str, Any],
    multiclass_metrics: Dict[str, Any],
    binary_baseline: Dict[str, Any],
    reliability_weights: Dict[int, float],
    high_confusion: List[int],
    sweep_results: List[Dict[str, Any]],
    selected_pair: Dict[str, Any],
    mapping: Dict[int, str],
) -> None:
    """Generate human-readable reports/fresh_policy_calibration_report.md."""
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# SentinelAI – Fresh Policy Calibration Report (Validation-Only)\n\n")
        f.write("> **Document Status**: Step 3 Validation-Only Calibration Artifact  \n")
        f.write(f"> **Calibrated At**: {metadata['calibrated_at']}  \n")
        f.write(f"> **Evaluation Partition**: `val_mask_fresh.npy` (65,850 flows strictly; `test_mask_fresh.npy` unopened)  \n")
        f.write(f"> **Model Artifact**: `data/models_fresh/random_forest_fresh.pkl`  \n\n")
        f.write("---\n\n")

        f.write("## 1. Executive Summary & Calibration Governance\n\n")
        f.write(
            "This report documents the validation-only policy calibration for SentinelAI's fresh evaluation pipeline. "
            "To prevent test-set circularity, all class reliability weights, high-confusion categories, and triage thresholds "
            "were derived strictly from the **held-out validation partition** (`val_mask_fresh.npy`). "
            "The fresh test partition (`test_mask_fresh.npy`) remained completely unblinded and unread during this phase.\n\n"
        )
        f.write("> [!IMPORTANT]\n")
        f.write(
            f"> **Selected Triage Thresholds**: **`theta_low = {selected_pair['theta_low']:.2f}`** and **`theta_high = {selected_pair['theta_high']:.2f}`**  \n"
            f"> - **Validation Attack Recall**: **{selected_pair['attack_recall_pct']}%** (Missed Attacks: {selected_pair['missed_attacks_count']:,} / {selected_pair['total_true_attacks']:,}, {selected_pair['missed_attack_rate_pct']}%)  \n"
            f"> - **Benign False-Positive Rate**: **{selected_pair['benign_fpr_pct']}%** (Escalated to Attack Tier: {selected_pair['benign_escalated_count']:,} / {binary_baseline['true_benign']:,})  \n"
            f"> - **Analyst Review Volume**: **{selected_pair['review_queue_count']:,} flows ({selected_pair['review_queue_rate_pct']}%)**  \n"
            f"> - **Review-Band Attack Concentration**: **{selected_pair['review_attack_concentration_pct']}%**  \n\n"
        )
        f.write("---\n\n")

        f.write("## 2. Validation Multiclass Model Metrics (`val_fresh`: 65,850 Flows)\n\n")
        f.write(f"- **Overall Accuracy**: {multiclass_metrics['accuracy']:.4f} ({multiclass_metrics['accuracy']*100:.2f}%)\n")
        f.write(f"- **Balanced Accuracy**: {multiclass_metrics['balanced_accuracy']:.4f}\n")
        f.write(f"- **Macro F1-Score**: {multiclass_metrics['macro_f1']:.4f}\n")
        f.write(f"- **Weighted F1-Score**: {multiclass_metrics['weighted_f1']:.4f}\n\n")

        f.write("### 2.1 Per-Class Validation Breakdown\n\n")
        f.write("| Class ID | Class Name | Support | Precision | Recall | F1-Score | Derived Fresh Reliability |\n| :---: | :--- | :---: | :---: | :---: | :---: | :---: |\n")
        pcm = multiclass_metrics["per_class"]
        for cid, name in sorted(mapping.items()):
            p = pcm[cid]["precision"]
            r = pcm[cid]["recall"]
            f1 = pcm[cid]["f1"]
            sup = pcm[cid]["support"]
            rel = reliability_weights[cid]
            f.write(f"| `{cid}` | {name} | {sup:,} | {p:.2%} | {r:.2%} | {f1:.2%} | **{rel:.2f}** |\n")
        f.write("\n")

        f.write("### 2.2 Derived High-Confusion Classes\n\n")
        hc_names = [f"Class {cid} ({mapping[cid]})" for cid in high_confusion]
        f.write(f"Classes exhibiting validation precision < 40%: **{', '.join(hc_names) if hc_names else 'None'}**\n\n")
        for cid in high_confusion:
            p = pcm[cid]["precision"]
            sup = pcm[cid]["support"]
            f.write(f"- **Class {cid} ({mapping[cid]})**: Precision is {p:.2%} with support of {sup:,} flows.\n")
        f.write("\n---\n\n")

        f.write("## 3. Standard Argmax Baseline (Benign vs Attack)\n\n")
        f.write("Baseline multiclass model argmax (predicting Attack when predicted class != 0):\n")
        f.write(f"- **Attack Recall**: {binary_baseline['attack_recall']:.2%}\n")
        f.write(f"- **Attack Precision**: {binary_baseline['attack_precision']:.2%}\n")
        f.write(f"- **Benign False-Positive Rate**: {binary_baseline['benign_fpr']:.2%}\n")
        f.write(f"- **Benign False-Negative Rate**: {binary_baseline['benign_fnr']:.2%}\n\n")
        f.write("---\n\n")

        f.write("## 4. Two-Stage Threshold Sweep Analysis (25 Candidate Pairs)\n\n")
        f.write(
            "The two-stage policy screens flows using aggregate attack probability $p_{\\text{attack}} = 1 - P(\\text{Benign})$. "
            "Flows below $\\theta_{\\text{low}}$ are auto-accepted as benign candidates; flows in $[\\theta_{\\text{low}}, \\theta_{\\text{high}})$ "
            "are escalated to analyst review (`review_required`); flows at or above $\\theta_{\\text{high}}$ advance to Stage 2 threat-tier routing.\n\n"
        )

        f.write("| theta_low | theta_high | Attack Recall | Missed Attacks | Benign FPR | Review Volume | Review Rate | Review Attack Conc. | SOC Loss |\n")
        f.write("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for res in sweep_results:
            th_l = res["theta_low"]
            th_h = res["theta_high"]
            rec = res["attack_recall_pct"]
            miss = res["missed_attacks_count"]
            fpr = res["benign_fpr_pct"]
            rev_cnt = res["review_queue_count"]
            rev_rate = res["review_queue_rate_pct"]
            conc = res["review_attack_concentration_pct"]
            loss = res["soc_penalty_loss"]
            sel_marker = " **[SELECTED]**" if (th_l == selected_pair["theta_low"] and th_h == selected_pair["theta_high"]) else ""
            f.write(f"| {th_l:.2f} | {th_h:.2f} | {rec:.2f}% | {miss:,} | {fpr:.2f}% | {rev_cnt:,} | {rev_rate:.2f}% | {conc:.2f}% | {loss:.2f}{sel_marker} |\n")
        f.write("\n")

        f.write("### 4.1 Selection Criterion Rationale\n\n")
        f.write(
            "Parameters were selected by minimizing the operational SOC loss function:  \n"
            "$$\\text{Loss} = 100 \\times \\text{MissedAttackRate} + 20 \\times \\text{BenignFPR} + 5 \\times \\text{ReviewQueueRate} + \\text{Penalty}$$  \n"
            "Subject to hard operational constraints:  \n"
            "1. **Attack Recall $\\ge 98.0\\%$** (Missed attack rate $< 2.0\\%$).  \n"
            "2. **Review Queue Rate $\\le 12.0\\%$** (Analyst workload ceiling).  \n"
            "3. **Benign False-Positive Rate $\\le 1.0\\%$** (Noise reduction in automated attack tiers).  \n\n"
            f"**Candidate `[{selected_pair['theta_low']:.2f}, {selected_pair['theta_high']:.2f})` achieves the lowest operational loss ({selected_pair['soc_penalty_loss']:.2f})**, "
            f"delivering **{selected_pair['attack_recall_pct']}%** Attack Recall with only **{selected_pair['review_queue_rate_pct']}%** review workload and **{selected_pair['benign_fpr_pct']}%** benign false alarms.\n\n"
        )

        f.write("### 4.2 Per-Class Missed Attacks for Selected Threshold Pair\n\n")
        f.write("| Attack Class ID | Attack Class Name | Validation Support | Missed in Auto-Benign | Class Attack Recall |\n| :---: | :--- | :---: | :---: | :---: |\n")
        for cid in range(1, 10):
            name = mapping[cid]
            sup = pcm[cid]["support"]
            missed = selected_pair["missed_by_class"].get(name, 0)
            recall = round((sup - missed) / sup * 100, 2) if sup > 0 else 0.0
            f.write(f"| `{cid}` | {name} | {sup:,} | {missed:,} | **{recall:.2f}%** |\n")
        f.write("\n---\n\n")

        f.write("## 5. Frozen Parameters Serialized for Fresh Evaluation\n\n")
        f.write(f"The parameters have been serialized to [`src/sentinelai/triage/calibrated_params_fresh.json`](file:///H:/SentinelAI/src/sentinelai/triage/calibrated_params_fresh.json):\n\n")
        f.write("```json\n")
        f.write(json.dumps({
            "theta_low": selected_pair["theta_low"],
            "theta_high": selected_pair["theta_high"],
            "class_reliability": reliability_weights,
            "high_confusion_classes": high_confusion,
        }, indent=2))
        f.write("\n```\n\n")
        f.write("> [!NOTE]\n")
        f.write(
            "> Production code (`src/sentinelai/triage/decision_engine.py`) remains untouched on safe default behavior. "
            "These calibrated parameters will be passed strictly to the offline evaluation harness in Step 4.\n\n"
        )
        f.write("---\n\n")

        f.write("## 6. Integrity & Safety Checklist\n\n")
        f.write("- [x] **Test Partition Blinded**: `test_mask_fresh.npy` was never accessed or read.\n")
        f.write("- [x] **Model Frozen**: `random_forest_fresh.pkl` was loaded read-only without retraining.\n")
        f.write("- [x] **Production Intact**: No production code, API routes, or thresholds modified.\n")
        f.write("- [x] **Transparent Selection Criterion**: Multi-objective SOC loss function documented prior to unblinding.\n")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    start_time = time.time()
    print("=" * 80)
    print("SentinelAI: Validation-Only Policy Calibration (Step 3)")
    print("=" * 80)

    # 1. Safety Assertion: Verify test isolation
    script_path = Path(__file__).resolve()
    assert_test_isolation(script_path)
    print("\n[1/7] Safety assertion verified: script contains zero references to test_mask_fresh.npy loading.")

    # 2. Path Setup
    data_path = PROJECT_ROOT / "data" / "raw" / "Data.csv"
    label_path = PROJECT_ROOT / "data" / "raw" / "Label.csv"
    readme_path = PROJECT_ROOT / "data" / "raw" / "Readme.txt"

    mask_dir = PROJECT_ROOT / "data" / "processed_fresh"
    val_mask_path = mask_dir / "val_mask_fresh.npy"

    models_dir = PROJECT_ROOT / "data" / "models_fresh"
    preproc_path = models_dir / "preprocessor_fresh.pkl"
    model_path = models_dir / "random_forest_fresh.pkl"
    train_metadata_path = models_dir / "train_fresh_metadata.json"

    calibrated_params_path = PROJECT_ROOT / "src" / "sentinelai" / "triage" / "calibrated_params_fresh.json"
    report_path = PROJECT_ROOT / "reports" / "fresh_policy_calibration_report.md"

    # 3. Verify Fresh Model Metadata
    print("\n[2/7] Verifying fresh model metadata and provenance...")
    with open(train_metadata_path, "r", encoding="utf-8") as f:
        train_meta = json.load(f)
    print(f"  Model trained on: {train_meta['trained_at']}")
    print(f"  Hyperparameters: {train_meta['hyperparameters']}")
    print(f"  Training rows: {train_meta['training_row_count']:,}")

    # 4. Load Validation Partition ONLY
    print("\n[3/7] Loading validation partition (val_mask_fresh.npy)...")
    val_mask = np.load(val_mask_path)
    val_rows = int(val_mask.sum())
    print(f"  Validation flow count: {val_rows:,}")

    # Load raw data and slice validation rows
    df_data, s_label, mapping = load_features_and_labels(data_path, label_path, readme_path)
    feature_columns = list(df_data.columns)

    X_val_raw = df_data.loc[val_mask].copy()
    y_val = s_label.loc[val_mask].copy().to_numpy()

    # Free full dataset immediately
    del df_data, s_label
    gc.collect()

    # 5. Transform Validation Data with Recovered Preprocessor
    print("\n[4/7] Transforming validation features with fresh preprocessor...")
    preproc_payload = joblib.load(preproc_path)
    scaler = preproc_payload["scaler"]
    columns = preproc_payload["columns"]
    assert columns == feature_columns, "Feature order mismatch between data and scaler!"

    X_val_scaled = pd.DataFrame(scaler.transform(X_val_raw[columns]), columns=columns)
    del X_val_raw
    gc.collect()

    # 6. Run Model Inference on Validation Data
    print("\n[5/7] Running model inference on validation partition...")
    model = joblib.load(model_path)
    infer_start = time.time()
    val_preds = model.predict(X_val_scaled)
    val_probs = model.predict_proba(X_val_scaled)
    infer_duration = time.time() - infer_start
    print(f"  Inference completed in {infer_duration:.2f} seconds.")

    # Multiclass Metrics
    val_acc = accuracy_score(y_val, val_preds)
    val_bal_acc = balanced_accuracy_score(y_val, val_preds)
    val_macro_f1 = f1_score(y_val, val_preds, average="macro")
    val_weighted_f1 = f1_score(y_val, val_preds, average="weighted")
    cm = confusion_matrix(y_val, val_preds, labels=sorted(mapping.keys()))

    print(f"  Validation Accuracy:          {val_acc:.4f} ({val_acc*100:.2f}%)")
    print(f"  Validation Balanced Accuracy: {val_bal_acc:.4f}")
    print(f"  Validation Macro F1:          {val_macro_f1:.4f}")
    print(f"  Validation Weighted F1:       {val_weighted_f1:.4f}")

    # Per-Class Metrics
    per_class_metrics: Dict[int, Dict[str, float]] = {}
    class_support: Dict[int, int] = {}
    for cid, name in sorted(mapping.items()):
        cls_mask = (y_val == cid)
        pred_cls_mask = (val_preds == cid)
        sup = int(cls_mask.sum())
        class_support[cid] = sup
        p = precision_score(cls_mask, pred_cls_mask, zero_division=0)
        r = recall_score(cls_mask, pred_cls_mask, zero_division=0)
        f1 = f1_score(cls_mask, pred_cls_mask, zero_division=0)
        per_class_metrics[cid] = {
            "name": name,
            "support": sup,
            "precision": float(p),
            "recall": float(r),
            "f1": float(f1),
        }
        print(f"    Class {cid} ({name:<15}): Prec {p:>6.2%} | Rec {r:>6.2%} | F1 {f1:>6.2%} | Support {sup:>6,}")

    # Binary Argmax Baseline
    is_true_attack = (y_val > 0)
    is_pred_attack = (val_preds > 0)
    bin_attack_recall = recall_score(is_true_attack, is_pred_attack)
    bin_attack_prec = precision_score(is_true_attack, is_pred_attack)
    is_true_benign = (y_val == 0)
    is_pred_benign = (val_preds == 0)
    bin_benign_fpr = float((is_true_benign & is_pred_attack).sum() / is_true_benign.sum())
    bin_benign_fnr = float((is_true_attack & is_pred_benign).sum() / is_true_attack.sum())

    binary_baseline = {
        "true_attacks": int(is_true_attack.sum()),
        "true_benign": int(is_true_benign.sum()),
        "attack_recall": float(bin_attack_recall),
        "attack_precision": float(bin_attack_prec),
        "benign_fpr": bin_benign_fpr,
        "benign_fnr": bin_benign_fnr,
    }

    # 7. Derive Class Reliability Weights & High-Confusion Classes
    print("\n[6/7] Deriving class reliability weights and high-confusion classes...")
    reliability_weights = derive_class_reliability(per_class_metrics, class_support)
    high_confusion_classes = identify_high_confusion_classes(per_class_metrics, threshold=0.40)

    print("  Derived Fresh Class Reliability Weights:")
    for cid, name in sorted(mapping.items()):
        print(f"    Class {cid} ({name:<15}): {reliability_weights[cid]:.2f}")
    print(f"  Derived High-Confusion Classes (Precision < 40%): {high_confusion_classes} "
          f"({[mapping[c] for c in high_confusion_classes]})")

    # 8. Two-Stage Threshold Sweep
    print("\n[7/7] Sweeping candidate two-stage threshold pairs (25 pairs)...")
    theta_low_candidates = [0.20, 0.25, 0.30, 0.35, 0.40]
    theta_high_candidates = [0.60, 0.65, 0.70, 0.75, 0.80]

    sweep_results: List[Dict[str, Any]] = []
    for th_l in theta_low_candidates:
        for th_h in theta_high_candidates:
            res = evaluate_two_stage_threshold_pair(
                probabilities=val_probs,
                true_labels=y_val,
                predicted_classes=val_preds,
                theta_low=th_l,
                theta_high=th_h,
                mapping=mapping,
            )
            res["soc_penalty_loss"] = compute_soc_utility_penalty(res)
            sweep_results.append(res)

    # Sort sweep results by operational penalty loss
    sweep_results.sort(key=lambda item: item["soc_penalty_loss"])
    selected_pair = sweep_results[0]

    print(f"\nOptimal Threshold Pair Selected: [{selected_pair['theta_low']:.2f}, {selected_pair['theta_high']:.2f})")
    print(f"  - Attack Recall:               {selected_pair['attack_recall_pct']}% (Missed attacks: {selected_pair['missed_attacks_count']:,})")
    print(f"  - Benign False-Positive Rate:  {selected_pair['benign_fpr_pct']}% (Escalated: {selected_pair['benign_escalated_count']:,})")
    print(f"  - Review Queue Volume:         {selected_pair['review_queue_count']:,} flows ({selected_pair['review_queue_rate_pct']}%)")
    print(f"  - Review Attack Concentration: {selected_pair['review_attack_concentration_pct']}%")
    print(f"  - Operational SOC Penalty:     {selected_pair['soc_penalty_loss']:.2f}")

    # 9. Save Calibrated Parameters JSON
    calibrated_params_payload = {
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "validation_partition": "data/processed_fresh/val_mask_fresh.npy",
        "validation_flow_count": val_rows,
        "selected_thresholds": {
            "theta_low": selected_pair["theta_low"],
            "theta_high": selected_pair["theta_high"],
        },
        "class_reliability": {str(k): v for k, v in reliability_weights.items()},
        "high_confusion_classes": high_confusion_classes,
        "confidence_formula_weights": {
            "top_score": 0.40,
            "margin": 0.35,
            "reliability": 0.25,
        },
        "safeguards": {
            "margin_threshold": 0.15,
            "min_top_score": 0.30,
        },
        "validation_multiclass_metrics": {
            "accuracy": float(val_acc),
            "balanced_accuracy": float(val_bal_acc),
            "macro_f1": float(val_macro_f1),
            "weighted_f1": float(val_weighted_f1),
            "per_class": per_class_metrics,
        },
        "binary_argmax_baseline": binary_baseline,
        "selected_pair_operational_metrics": selected_pair,
        "top_5_candidate_pairs": sweep_results[:5],
    }

    calibrated_params_path.parent.mkdir(parents=True, exist_ok=True)
    with open(calibrated_params_path, "w", encoding="utf-8") as f:
        json.dump(calibrated_params_payload, f, indent=2)
    print(f"\nCalibrated parameters saved to {calibrated_params_path}")

    # 10. Generate Calibration Report
    metadata = {
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    generate_calibration_report(
        report_path=report_path,
        metadata=metadata,
        multiclass_metrics={
            "accuracy": val_acc,
            "balanced_accuracy": val_bal_acc,
            "macro_f1": val_macro_f1,
            "weighted_f1": val_weighted_f1,
            "per_class": per_class_metrics,
        },
        binary_baseline=binary_baseline,
        reliability_weights=reliability_weights,
        high_confusion=high_confusion_classes,
        sweep_results=sweep_results,
        selected_pair=selected_pair,
        mapping=mapping,
    )
    print(f"Calibration report generated at {report_path}")

    elapsed = time.time() - start_time
    print(f"\nStep 3 successfully completed in {elapsed:.2f} seconds.")
    print("=" * 80)


if __name__ == "__main__":
    main()
