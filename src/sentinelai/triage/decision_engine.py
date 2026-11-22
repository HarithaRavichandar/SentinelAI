# src/sentinelai/triage/decision_engine.py
"""Deterministic, confidence-aware cybersecurity triage decision engine for SentinelAI (Laya).

Evolves Laya from a purely conversational text explanation into a structured,
verifiable triage decision component. This module implements:
1. A typed decision contract (TriageDecision) using Pydantic.
2. A deterministic cybersecurity triage policy that maps model predictions,
   score margins, class reliability, and feature evidence into actionable decisions.
3. Safe guardrails: non-destructive recommendations, explicit human-review triggers,
   and resilience against LLM and SHAP failures.
"""

from __future__ import annotations

from enum import Enum
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

# Feature flag & threshold constants for experimental two-stage triage policy
FEATURE_FLAG_TWO_STAGE = "SENTINELAI_TWO_STAGE_TRIAGE"
TWO_STAGE_TH_LOW = 0.20
TWO_STAGE_TH_HIGH = 0.70

CALIBRATED_PARAMS_PATH = Path(__file__).resolve().parent / "calibrated_params_fresh.json"


class PolicyConfigurationError(RuntimeError):
    """Raised when the calibrated policy parameters file is missing, malformed, or invalid."""
    pass


_CACHED_CALIBRATED_PARAMS: Optional[Dict[str, Any]] = None


def load_calibrated_params(
    params_path: Optional[Path] = None,
    force_reload: bool = False,
) -> Dict[str, Any]:
    """Load and validate the frozen fresh validation-calibrated triage parameters.

    Strictly validates required keys, data types, threshold ranges, and class
    mappings. Fails clearly if the file is missing, malformed, or incomplete.
    Never silently substitutes legacy values.
    """
    global _CACHED_CALIBRATED_PARAMS
    if not force_reload and _CACHED_CALIBRATED_PARAMS is not None and params_path is None:
        return _CACHED_CALIBRATED_PARAMS

    resolved_path = params_path or CALIBRATED_PARAMS_PATH

    if not resolved_path.exists():
        raise PolicyConfigurationError(
            f"Calibrated policy parameters file not found at: {resolved_path}"
        )

    try:
        with open(resolved_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise PolicyConfigurationError(
            f"Malformed JSON in calibration file '{resolved_path}': {exc}"
        ) from exc
    except Exception as exc:
        raise PolicyConfigurationError(
            f"Failed to read calibration file '{resolved_path}': {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise PolicyConfigurationError(
            f"Calibration payload must be a JSON object, got {type(data).__name__}"
        )

    # 1. Validate selected_thresholds
    if "selected_thresholds" not in data:
        raise PolicyConfigurationError("Missing required key 'selected_thresholds' in calibration parameters.")
    thresholds = data["selected_thresholds"]
    if not isinstance(thresholds, dict):
        raise PolicyConfigurationError("'selected_thresholds' must be a dictionary.")
    for key in ("theta_low", "theta_high"):
        if key not in thresholds:
            raise PolicyConfigurationError(f"Missing threshold key '{key}' in 'selected_thresholds'.")
        val = thresholds[key]
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val):
            raise PolicyConfigurationError(f"Threshold '{key}' must be a finite float, got {val!r}")
        if val < 0.0 or val > 1.0:
            raise PolicyConfigurationError(f"Threshold '{key}' out of bounds [0.0, 1.0]: {val}")

    theta_low = float(thresholds["theta_low"])
    theta_high = float(thresholds["theta_high"])
    if theta_low >= theta_high:
        raise PolicyConfigurationError(
            f"Invalid threshold ordering: theta_low ({theta_low}) must be strictly less than theta_high ({theta_high})."
        )

    # 2. Validate class_reliability
    if "class_reliability" not in data:
        raise PolicyConfigurationError("Missing required key 'class_reliability' in calibration parameters.")
    rel = data["class_reliability"]
    if not isinstance(rel, dict):
        raise PolicyConfigurationError("'class_reliability' must be a dictionary.")

    parsed_reliability: Dict[int, float] = {}
    for cid in range(10):
        val = rel.get(str(cid)) if str(cid) in rel else rel.get(cid)
        if val is None:
            raise PolicyConfigurationError(f"Missing reliability score for class {cid} in 'class_reliability'.")
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val):
            raise PolicyConfigurationError(f"Reliability for class {cid} must be a finite float, got {val!r}")
        if val < 0.0 or val > 1.0:
            raise PolicyConfigurationError(f"Reliability for class {cid} out of bounds [0.0, 1.0]: {val}")
        parsed_reliability[cid] = float(val)

    # 3. Validate high_confusion_classes
    if "high_confusion_classes" not in data:
        raise PolicyConfigurationError("Missing required key 'high_confusion_classes' in calibration parameters.")
    h_conf = data["high_confusion_classes"]
    if not isinstance(h_conf, (list, set, tuple)):
        raise PolicyConfigurationError("'high_confusion_classes' must be a list of class IDs.")
    parsed_high_confusion: Set[int] = set()
    for item in h_conf:
        if not isinstance(item, int) or isinstance(item, bool) or item < 0 or item > 9:
            raise PolicyConfigurationError(f"Invalid class ID in 'high_confusion_classes': {item!r}")
        parsed_high_confusion.add(item)

    # 4. Validate confidence_formula_weights
    weights = data.get("confidence_formula_weights", {"top_score": 0.40, "margin": 0.35, "reliability": 0.25})
    if not isinstance(weights, dict):
        raise PolicyConfigurationError("'confidence_formula_weights' must be a dictionary.")
    for w_key in ("top_score", "margin", "reliability"):
        if w_key not in weights or not isinstance(weights[w_key], (int, float)):
            raise PolicyConfigurationError(f"Invalid or missing weight '{w_key}' in 'confidence_formula_weights'.")

    # 5. Validate safeguards
    safeguards = data.get("safeguards", {"margin_threshold": 0.15, "min_top_score": 0.30})
    if not isinstance(safeguards, dict):
        raise PolicyConfigurationError("'safeguards' must be a dictionary.")

    validated_payload = {
        "theta_low": theta_low,
        "theta_high": theta_high,
        "class_reliability": parsed_reliability,
        "high_confusion_classes": parsed_high_confusion,
        "confidence_formula_weights": weights,
        "safeguards": safeguards,
        "raw_json": data,
    }

    if params_path is None:
        _CACHED_CALIBRATED_PARAMS = validated_payload

    return validated_payload


def is_two_stage_enabled() -> bool:
    """Check whether the experimental two-stage triage policy is enabled via environment.

    Defaults to False (disabled) unless explicitly opted in via
    SENTINELAI_TWO_STAGE_TRIAGE=true/1/yes/on.
    """
    val = os.getenv(FEATURE_FLAG_TWO_STAGE, "").strip().lower()
    return val in ("1", "true", "yes", "on")


def extract_p_attack(probabilities: Any) -> Tuple[Optional[float], Optional[str]]:
    """Extract and validate aggregate attack score p_attack = 1 - P(Benign) from model scores.

    Parameters:
        probabilities: Mapping from class ID (0..9 or '0'..'9') to model scores.

    Returns:
        (p_attack, error_reason)
        If valid: (float in [0.0, 1.0], None)
        If invalid/missing: (None, descriptive_error_string)
    """
    if not isinstance(probabilities, dict) or not probabilities:
        return None, "Model probabilities payload is empty or not a dictionary."

    p_benign = probabilities.get(0)
    if p_benign is None and "0" in probabilities:
        p_benign = probabilities.get("0")

    if p_benign is None:
        return None, "Class 0 (Benign) score is missing from probabilities."

    if not isinstance(p_benign, (int, float)) or not math.isfinite(p_benign) or p_benign < 0.0 or p_benign > 1.0:
        return None, f"Invalid Benign score ({p_benign}); must be a finite number in [0.0, 1.0]."

    valid_scores = []
    for k, v in probabilities.items():
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0.0:
            return None, f"Probability for class {k} is invalid or non-finite ({v})."
        valid_scores.append(float(v))

    total_sum = sum(valid_scores)
    if total_sum < 0.50 or total_sum > 1.50:
        return None, f"Abnormal probability distribution sum ({total_sum:.3f}); expected normalized distribution ~1.0."

    p_attack = max(0.0, min(1.0, 1.0 - float(p_benign)))
    return round(p_attack, 6), None


class AlertPriority(str, Enum):
    """Operational urgency level for security analyst response."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW_REQUIRED = "review_required"


class DecisionStatus(str, Enum):
    """System confidence state of the advisory triage assessment.

    Meanings:
    - ACCEPTED: Advisory assessment meets confidence criteria and clear separation
      for standard triage routing. Does NOT confirm an attack or execute any operational action.
    - REVIEW_REQUIRED: Advisory assessment exhibits ambiguity, narrow score margin,
      low confidence, or a high-confusion class, requiring human analyst review before routing.
    - UNAVAILABLE: Advisory decision cannot be computed due to missing, invalid,
      or malformed inputs or model failure.
    """
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    UNAVAILABLE = "unavailable"


class TriageDecision(BaseModel):
    """Structured contract for cybersecurity alert triage decisions."""
    predicted_class: str = Field(
        ...,
        description="Human-readable traffic classification from the model",
    )
    priority: AlertPriority = Field(
        ...,
        description="Assigned triage priority level based on threat severity and confidence",
    )
    recommended_action: str = Field(
        ...,
        description=(
            "Advisory operational recommendation for security analysts. Non-destructive; "
            "no automated traffic blocking, host isolation, or network reconfiguration is executed."
        ),
    )
    decision_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Heuristic composite confidence score (0.0 to 1.0) combining vote share, "
            "margin separation, and empirical class reliability; not a calibrated probability."
        ),
    )
    decision_status: DecisionStatus = Field(
        ...,
        description=(
            "Advisory execution status: 'accepted' indicates recommendation meets confidence criteria "
            "(does NOT imply attack confirmation or action execution); 'review_required' indicates "
            "analyst review needed; 'unavailable' indicates missing or invalid inputs."
        ),
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Empirical observations and model signals supporting the advisory decision",
    )
    uncertainty_reasons: List[str] = Field(
        default_factory=list,
        description="Specific reasons triggering caution, ambiguity, or human escalation",
    )
    requires_human_review: bool = Field(
        ...,
        description="True if an analyst must review the alert before operational response",
    )
    policy_mode: Optional[str] = Field(
        default=None,
        description="Triage policy variant used: 'legacy' or 'two_stage_experimental'",
    )


# Empirical class reliability weights derived from held-out test evaluation
# (reports/model_validation_report.md, test partition: 67,188 flows).
# For classes with high test support and high precision/F1, the metric is well-justified.
# For classes with small sample size or low recall, a conservative fallback is applied:
CLASS_RELIABILITY: Dict[int, float] = {
    0: 0.98,  # Benign: Precision 99.16%, Recall 98.13%, F1 98.64%, Support 53,562 (79.72% of split)
    1: 0.35,  # Analysis: Precision 35.42%, Recall 28.33%, F1 31.48%, Support 60 (high confusion class)
    2: 0.65,  # Backdoor: Precision 84.78%, Recall 53.42%, F1 65.55%, Support 73 (conservative fallback: F1 used due to small support and low recall)
    3: 0.40,  # DoS: Precision 40.24%, Recall 28.65%, F1 33.47%, Support 691 (frequently confused with Exploits)
    4: 0.75,  # Exploits: Precision 74.80%, Recall 78.60%, F1 76.65%, Support 4,612 (well-supported attack class)
    5: 0.65,  # Fuzzers: Precision 62.16%, Recall 73.97%, F1 67.55%, Support 4,564
    6: 0.55,  # Generic: Precision 52.39%, Recall 72.93%, F1 60.98%, Support 676
    7: 0.65,  # Reconnaissance: Precision 65.08%, Recall 39.30%, F1 49.01%, Support 2,613
    8: 0.10,  # Shellcode: Precision 8.99%, Recall 22.73%, F1 12.88%, Support 308 (extreme false positive confusion)
    9: 0.45,  # Worms: Precision 52.17%, Recall 41.38%, F1 46.15%, Support 29 (conservative fallback due to very low support)
}

# Criticality tier definition
CRITICAL_CLASSES = {2, 4, 9}   # Backdoor, Exploits, Worms
HIGH_CLASSES = {3, 5}           # DoS, Fuzzers
MEDIUM_CLASSES = {6, 7}         # Generic, Reconnaissance
HIGH_CONFUSION_CLASSES = {1, 8} # Analysis, Shellcode


def compute_decision_confidence(
    class_id: int,
    probabilities: Dict[int, float],
    reliability_map: Optional[Dict[int, float]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, float, float, Optional[int], Optional[int]]:
    """Compute heuristic composite decision confidence, score margin, and identify runner-up.

    Parameters:
        class_id: Predicted class index.
        probabilities: Mapping from class ID to score.
        reliability_map: Optional class-to-reliability map. If None, uses legacy CLASS_RELIABILITY.
        weights: Optional dictionary with top_score, margin, reliability weights.

    Note:
        This is a heuristic operational score, not a calibrated statistical probability.

    Returns:
        (confidence, top_score, margin, top_id, runner_up_id)
    """
    if not probabilities or not isinstance(probabilities, dict):
        return 0.0, 0.0, 0.0, None, None

    # Filter valid finite non-negative values
    valid_scores = {
        int(k): float(v)
        for k, v in probabilities.items()
        if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0.0
    }
    if not valid_scores:
        return 0.0, 0.0, 0.0, None, None

    sorted_scores = sorted(valid_scores.items(), key=lambda item: item[1], reverse=True)
    top_id, top_score = sorted_scores[0]
    runner_up_id, runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else (None, 0.0)

    margin = max(0.0, top_score - runner_up_score)
    active_rel = reliability_map if reliability_map is not None else CLASS_RELIABILITY
    reliability = active_rel.get(class_id, 0.30)  # Conservative fallback for unknown classes

    # Composite confidence formula
    active_weights = weights if weights is not None else {"top_score": 0.40, "margin": 0.35, "reliability": 0.25}
    w_top = active_weights.get("top_score", 0.40)
    w_margin = active_weights.get("margin", 0.35)
    w_rel = active_weights.get("reliability", 0.25)

    composite = w_top * top_score + w_margin * margin + w_rel * reliability
    bounded_confidence = round(min(1.0, max(0.0, composite)), 3)

    return bounded_confidence, top_score, margin, top_id, runner_up_id


def evaluate_triage_decision(
    prediction: Dict[str, Any],
    shap_result: Optional[Dict[str, float]] = None,
    raw_features: Optional[Dict[str, Any]] = None,
    two_stage_mode: Optional[bool] = None,
    model_version: Optional[str] = None,
) -> TriageDecision:
    """Evaluate a deterministic, confidence-aware triage decision.

    Parameters:
        prediction: Dictionary from InferenceEngine containing class_id, class_label, probabilities.
        shap_result: Optional dictionary of feature contributions for the predicted class.
        raw_features: Optional dictionary of raw input features.
        two_stage_mode: Optional boolean flag to enable experimental two-stage triage policy.
                       If None, reads from SENTINELAI_TWO_STAGE_TRIAGE env variable (default: False).
        model_version: Optional string indicating model version ('legacy' or 'fresh').
                       If None, extracts from prediction dict or SENTINELAI_MODEL_VERSION env var.

    Returns:
        TriageDecision instance.
    """
    if two_stage_mode is None:
        two_stage_mode = is_two_stage_enabled()

    policy_mode = "two_stage_experimental" if two_stage_mode else "legacy"

    # Resolve model version for pairing verification
    if model_version is None and isinstance(prediction, dict):
        model_version = prediction.get("model_version")
    if model_version is None:
        model_version = os.getenv("SENTINELAI_MODEL_VERSION", "legacy").strip().lower()

    # Load frozen calibrated parameters in experimental mode; fail clearly if missing or invalid
    if two_stage_mode:
        calib = load_calibrated_params()
        th_low = calib["theta_low"]
        th_high = calib["theta_high"]
        active_reliability = calib["class_reliability"]
        active_high_confusion = calib["high_confusion_classes"]
        active_weights = calib["confidence_formula_weights"]
        active_safeguards = calib["safeguards"]
    else:
        th_low = TWO_STAGE_TH_LOW
        th_high = TWO_STAGE_TH_HIGH
        active_reliability = CLASS_RELIABILITY
        active_high_confusion = HIGH_CONFUSION_CLASSES
        active_weights = {"top_score": 0.40, "margin": 0.35, "reliability": 0.25}
        active_safeguards = {"margin_threshold": 0.15, "min_top_score": 0.30}

    evidence: List[str] = []
    uncertainty_reasons: List[str] = []

    if not isinstance(prediction, dict):
        return TriageDecision(
            predicted_class="Unknown",
            priority=AlertPriority.REVIEW_REQUIRED,
            recommended_action="escalate_to_tier2_analyst",
            decision_confidence=0.0,
            decision_status=DecisionStatus.UNAVAILABLE,
            evidence=["Prediction payload is missing or invalid."],
            uncertainty_reasons=["Prediction input is not a valid dictionary."],
            requires_human_review=True,
            policy_mode=policy_mode,
        )

    class_id = prediction.get("class_id")
    class_label = str(prediction.get("class_label", "Unknown"))
    probabilities = prediction.get("probabilities", {})

    # Check for missing/malformed classification input
    if class_id is None or not isinstance(class_id, int) or class_label in {"Unknown", ""}:
        return TriageDecision(
            predicted_class="Unknown",
            priority=AlertPriority.REVIEW_REQUIRED,
            recommended_action="escalate_to_tier2_analyst",
            decision_confidence=0.0,
            decision_status=DecisionStatus.UNAVAILABLE,
            evidence=["Model prediction could not be determined or is missing."],
            uncertainty_reasons=["Classification output is missing or invalid."],
            requires_human_review=True,
            policy_mode=policy_mode,
        )

    # Compute confidence metrics using active reliability weights
    confidence, top_score, margin, top_id, runner_up_id = compute_decision_confidence(
        class_id,
        probabilities,
        reliability_map=active_reliability,
        weights=active_weights,
    )

    evidence.append(f"Model classified flow as '{class_label}' (ID {class_id}) with vote share {top_score:.3f}.")
    if runner_up_id is not None and probabilities:
        runner_up_score = probabilities.get(runner_up_id, 0.0)
        evidence.append(f"Separation margin over runner-up (ID {runner_up_id}) is {margin:.3f} (runner-up score: {runner_up_score:.3f}).")

    # Evaluate SHAP evidence if available
    if isinstance(shap_result, dict) and shap_result:
        top_positive_shap = sorted(
            [(k, v) for k, v in shap_result.items() if math.isfinite(v) and v > 0],
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        if top_positive_shap:
            shap_desc = ", ".join(f"{k} (+{v:.3f})" for k, v in top_positive_shap)
            evidence.append(f"Top SHAP features driving '{class_label}' score: {shap_desc}.")
            evidence.append(
                f"Attribution note: SHAP feature contributions reflect mathematical attribution toward the '{class_label}' score and do not constitute proof of malicious intent."
            )
        
        # Check for opposing SHAP signals
        opposing_shap = [k for k, v in shap_result.items() if math.isfinite(v) and v < -0.1]
        if len(opposing_shap) >= 3:
            uncertainty_reasons.append(f"Multiple significant opposing SHAP features detected for {class_label}: {len(opposing_shap)} features.")
    else:
        evidence.append("Attribution note: SHAP explanations not computed or unavailable for this flow.")

    # -------------------------------------------------------------------------
    # Policy Evaluation Rules
    # -------------------------------------------------------------------------
    if two_stage_mode:
        p_attack, p_attack_err = extract_p_attack(probabilities)
        if p_attack_err is not None:
            uncertainty_reasons.append(f"Two-stage triage: {p_attack_err}")
            evidence.append("Two-stage triage policy active: invalid probability distribution detected.")
            return TriageDecision(
                predicted_class=class_label,
                priority=AlertPriority.MEDIUM,
                recommended_action="inspect_uncertain_traffic_and_review",
                decision_confidence=confidence,
                decision_status=DecisionStatus.REVIEW_REQUIRED,
                evidence=evidence,
                uncertainty_reasons=uncertainty_reasons,
                requires_human_review=True,
                policy_mode="two_stage_experimental",
            )

        evidence.append(
            f"Two-stage triage policy active: aggregate attack score p_attack={p_attack:.3f} "
            f"(calibrated thresholds: theta_low={th_low:.2f}, theta_high={th_high:.2f})."
        )

        # Model-policy pairing verification
        if model_version == "fresh":
            evidence.append("Validated configuration: fresh model paired with fresh validation-calibrated two-stage policy.")
        elif model_version == "legacy":
            evidence.append(
                "Operational warning: Experimental two-stage policy was calibrated on fresh validation data; "
                "operating with legacy model lacks matching validation guarantees."
            )
            uncertainty_reasons.append("Unvalidated pairing: experimental two-stage policy applied to legacy model predictions.")

        if p_attack < th_low:
            evidence.append(
                f"Stage 1 screening: p_attack={p_attack:.3f} (< {th_low:.2f} threshold). "
                "Classified as benign candidate for standard monitoring."
            )
            return TriageDecision(
                predicted_class=class_label,
                priority=AlertPriority.LOW,
                recommended_action="allow_and_standard_monitoring",
                decision_confidence=confidence,
                decision_status=DecisionStatus.ACCEPTED,
                evidence=evidence,
                uncertainty_reasons=uncertainty_reasons,
                requires_human_review=False,
                policy_mode="two_stage_experimental",
            )

        elif p_attack < th_high:
            evidence.append(
                f"Stage 1 screening: p_attack={p_attack:.3f} falls in uncertainty review band "
                f"[{th_low:.2f}, {th_high:.2f}). Escalated to analyst review."
            )
            uncertainty_reasons.append(
                f"Ambiguous attack probability (p_attack={p_attack:.3f} in "
                f"[{th_low:.2f}, {th_high:.2f})); analyst inspection required."
            )
            return TriageDecision(
                predicted_class=class_label,
                priority=AlertPriority.MEDIUM,
                recommended_action="inspect_uncertain_traffic_and_review",
                decision_confidence=confidence,
                decision_status=DecisionStatus.REVIEW_REQUIRED,
                evidence=evidence,
                uncertainty_reasons=uncertainty_reasons,
                requires_human_review=True,
                policy_mode="two_stage_experimental",
            )

        else:
            evidence.append(
                f"Stage 1 screening: p_attack={p_attack:.3f} (>= {th_high:.2f} threshold). "
                "Advancing to Stage 2 threat-tier and operational evaluation."
            )
            if class_id == 0:
                uncertainty_reasons.append(
                    f"Fragmented attack signal: p_attack={p_attack:.3f} >= {th_high:.2f} despite Benign plurality."
                )

    requires_human_review = False
    decision_status = DecisionStatus.ACCEPTED

    # 0. Check for conflicting prediction / argmax mismatch
    if top_id is not None and top_id != class_id:
        decision_status = DecisionStatus.REVIEW_REQUIRED
        requires_human_review = True
        uncertainty_reasons.append(
            f"Conflicting evidence: predicted class_id ({class_id}) differs from highest-vote class ({top_id})."
        )

    # 1. Close competition / narrow margin check
    margin_threshold = active_safeguards.get("margin_threshold", 0.15)
    if probabilities and margin < margin_threshold:
        decision_status = DecisionStatus.REVIEW_REQUIRED
        requires_human_review = True
        uncertainty_reasons.append(
            f"Narrow score margin ({margin:.3f} < {margin_threshold:.2f}); close competition between top classes."
        )

    # 2. Historical high-confusion classes check
    if class_id in active_high_confusion:
        decision_status = DecisionStatus.REVIEW_REQUIRED
        requires_human_review = True
        uncertainty_reasons.append(
            f"Class '{class_label}' exhibits low empirical precision ({active_reliability.get(class_id, 0.0):.0%}) in validation."
        )

    # 3. Score distribution validity check (empty, non-finite, abnormal sum, or weak signal)
    min_top_score = active_safeguards.get("min_top_score", 0.30)
    if not probabilities or top_score <= 0.0:
        decision_status = DecisionStatus.REVIEW_REQUIRED
        requires_human_review = True
        uncertainty_reasons.append("Model score distribution is empty or zero.")
    else:
        # Check for abnormal score sum (expected normalized ~1.0)
        score_sum = sum(
            float(v)
            for v in probabilities.values()
            if isinstance(v, (int, float)) and math.isfinite(v)
        )
        if score_sum < 0.50 or score_sum > 1.50:
            decision_status = DecisionStatus.REVIEW_REQUIRED
            requires_human_review = True
            uncertainty_reasons.append(
                f"Abnormal score distribution sum ({score_sum:.3f}); expected normalized distribution ~1.0."
            )
        # Check for weak top classification signal
        if top_score < min_top_score:
            decision_status = DecisionStatus.REVIEW_REQUIRED
            requires_human_review = True
            uncertainty_reasons.append(
                f"Low top model score ({top_score:.3f} < {min_top_score:.2f}); weak classification signal."
            )

    # 4. Route priority and recommended action based on threat tier and confidence
    if class_id == 0:  # Benign
        if margin >= 0.30 and not uncertainty_reasons:
            priority = AlertPriority.LOW
            recommended_action = "allow_and_standard_monitoring"
            requires_human_review = False
        else:
            priority = AlertPriority.MEDIUM
            decision_status = DecisionStatus.REVIEW_REQUIRED
            recommended_action = "verify_benign_classification"
            requires_human_review = True
            if not uncertainty_reasons:
                uncertainty_reasons.append("Benign classification exhibits low score margin or non-trivial attack scores.")

    elif class_id in CRITICAL_CLASSES:  # Exploits, Backdoor, Worms
        if confidence >= 0.70 and margin >= 0.20:
            priority = AlertPriority.CRITICAL
            recommended_action = "isolate_workstation_and_open_incident"
            requires_human_review = True  # Critical threats always require analyst sign-off
        else:
            priority = AlertPriority.HIGH
            decision_status = DecisionStatus.REVIEW_REQUIRED
            recommended_action = "quarantine_traffic_and_escalate"
            requires_human_review = True
            uncertainty_reasons.append(f"Critical class '{class_label}' below automated confidence threshold (confidence={confidence:.3f}).")

    elif class_id in HIGH_CLASSES:  # DoS, Fuzzers
        if confidence >= 0.65 and not requires_human_review:
            priority = AlertPriority.HIGH
            recommended_action = "apply_rate_limiting_and_capture_pcap"
        else:
            priority = AlertPriority.MEDIUM
            decision_status = DecisionStatus.REVIEW_REQUIRED
            recommended_action = "inspect_connection_pool_and_review"
            requires_human_review = True
            if not uncertainty_reasons:
                uncertainty_reasons.append(f"Moderate confidence for {class_label} (confidence={confidence:.3f}).")

    elif class_id in MEDIUM_CLASSES:  # Generic, Reconnaissance
        if confidence >= 0.60 and not requires_human_review:
            priority = AlertPriority.MEDIUM
            recommended_action = "log_source_ip_and_monitor_thresholds"
        else:
            priority = AlertPriority.MEDIUM
            decision_status = DecisionStatus.REVIEW_REQUIRED
            recommended_action = "review_source_host_activity"
            requires_human_review = True

    elif class_id == 8:  # Shellcode
        priority = AlertPriority.HIGH
        decision_status = DecisionStatus.REVIEW_REQUIRED
        recommended_action = "manual_deep_packet_inspection"
        requires_human_review = True

    elif class_id == 1:  # Analysis
        priority = AlertPriority.MEDIUM
        decision_status = DecisionStatus.REVIEW_REQUIRED
        recommended_action = "review_network_diagnostics_log"
        requires_human_review = True

    else:
        priority = AlertPriority.REVIEW_REQUIRED
        decision_status = DecisionStatus.REVIEW_REQUIRED
        recommended_action = "escalate_to_tier2_analyst"
        requires_human_review = True

    return TriageDecision(
        predicted_class=class_label,
        priority=priority,
        recommended_action=recommended_action,
        decision_confidence=confidence,
        decision_status=decision_status,
        evidence=evidence,
        uncertainty_reasons=uncertainty_reasons,
        requires_human_review=requires_human_review,
        policy_mode=policy_mode,
    )
