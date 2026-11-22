# tests/test_calibrated_policy.py
"""Tests for validation-calibrated parameters in SentinelAI's experimental two-stage decision engine."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sentinelai.triage.decision_engine import (
    AlertPriority,
    DecisionStatus,
    FEATURE_FLAG_TWO_STAGE,
    HIGH_CONFUSION_CLASSES,
    CLASS_RELIABILITY,
    CALIBRATED_PARAMS_PATH,
    PolicyConfigurationError,
    TriageDecision,
    compute_decision_confidence,
    evaluate_triage_decision,
    is_two_stage_enabled,
    load_calibrated_params,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure clean feature flag environment and cache reset for each test."""
    monkeypatch.delenv(FEATURE_FLAG_TWO_STAGE, raising=False)
    # Clear parameter cache to ensure clean test state
    import sentinelai.triage.decision_engine as de
    de._CACHED_CALIBRATED_PARAMS = None
    yield
    de._CACHED_CALIBRATED_PARAMS = None


def test_legacy_default_behavior_unchanged():
    """When feature flag is OFF, legacy policy evaluates with legacy parameters."""
    assert is_two_stage_enabled() is False

    pred_benign = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.90, 4: 0.05, 3: 0.05},
    }
    decision = evaluate_triage_decision(pred_benign, two_stage_mode=False)
    assert decision.policy_mode == "legacy"
    assert decision.priority == AlertPriority.LOW
    assert decision.decision_status == DecisionStatus.ACCEPTED
    assert decision.requires_human_review is False
    assert not any("Two-stage triage policy active" in e for e in decision.evidence)

    # Legacy high confusion class (Shellcode = 8) triggers review under legacy policy
    pred_shellcode = {
        "class_id": 8,
        "class_label": "Shellcode",
        "probabilities": {8: 0.80, 0: 0.20},
    }
    dec_sc = evaluate_triage_decision(pred_shellcode, two_stage_mode=False)
    assert dec_sc.policy_mode == "legacy"
    assert dec_sc.priority == AlertPriority.HIGH
    assert dec_sc.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_sc.requires_human_review is True
    # Verify legacy reliability (10%) is reported
    assert any("10%" in u for u in dec_sc.uncertainty_reasons)


def test_experimental_mode_loads_fresh_calibrated_parameters(monkeypatch):
    """When feature flag is ON, frozen validation-calibrated parameters are loaded."""
    monkeypatch.setenv(FEATURE_FLAG_TWO_STAGE, "true")
    assert is_two_stage_enabled() is True

    calib = load_calibrated_params()
    # Verify frozen thresholds
    assert calib["theta_low"] == 0.20
    assert calib["theta_high"] == 0.70

    # Verify class reliabilities match calibrated_params_fresh.json
    assert calib["class_reliability"][0] == 0.98   # Benign
    assert calib["class_reliability"][1] == 0.22   # Analysis
    assert calib["class_reliability"][2] == 0.63   # Backdoor
    assert calib["class_reliability"][3] == 0.39   # DoS
    assert calib["class_reliability"][4] == 0.76   # Exploits
    assert calib["class_reliability"][5] == 0.63   # Fuzzers
    assert calib["class_reliability"][6] == 0.81   # Generic
    assert calib["class_reliability"][7] == 0.62   # Reconnaissance
    assert calib["class_reliability"][8] == 0.32   # Shellcode
    assert calib["class_reliability"][9] == 0.43   # Worms

    # Verify high-confusion classes on fresh split (only class 1)
    assert calib["high_confusion_classes"] == {1}


def test_frozen_thresholds_exact_boundary():
    """Verify exact threshold boundary behavior for theta_low=0.20 and theta_high=0.70."""
    # 1. p_attack = 0.199 < 0.20 -> Zone 1 (Auto-Benign, LOW priority, ACCEPTED, review=False)
    pred_zone1 = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.801, 4: 0.199},
    }
    dec_zone1 = evaluate_triage_decision(pred_zone1, two_stage_mode=True)
    assert dec_zone1.priority == AlertPriority.LOW
    assert dec_zone1.decision_status == DecisionStatus.ACCEPTED
    assert dec_zone1.requires_human_review is False
    assert any("p_attack=0.199 (< 0.20 threshold)" in e for e in dec_zone1.evidence)

    # 2. p_attack = 0.200 == 0.20 -> Zone 2 (Review Band: MEDIUM priority, REVIEW_REQUIRED, review=True)
    pred_boundary_low = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.800, 4: 0.200},
    }
    dec_b_low = evaluate_triage_decision(pred_boundary_low, two_stage_mode=True)
    assert dec_b_low.priority == AlertPriority.MEDIUM
    assert dec_b_low.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_b_low.requires_human_review is True
    assert any("falls in uncertainty review band [0.20, 0.70)" in e for e in dec_b_low.evidence)

    # 3. p_attack = 0.699 < 0.70 -> Zone 2 (Review Band)
    pred_boundary_high_under = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.301, 4: 0.699},
    }
    dec_b_high_under = evaluate_triage_decision(pred_boundary_high_under, two_stage_mode=True)
    assert dec_b_high_under.priority == AlertPriority.MEDIUM
    assert dec_b_high_under.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_b_high_under.requires_human_review is True

    # 4. p_attack = 0.700 == 0.70 -> Zone 3 (Stage 2 Threat-Tier Escalation)
    pred_zone3 = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.300, 4: 0.700},
    }
    dec_zone3 = evaluate_triage_decision(pred_zone3, two_stage_mode=True)
    assert dec_zone3.priority == AlertPriority.HIGH
    assert dec_zone3.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_zone3.recommended_action == "quarantine_traffic_and_escalate"
    assert any("Advancing to Stage 2 threat-tier" in e for e in dec_zone3.evidence)


def test_missing_parameter_file_fails_clearly(tmp_path):
    """Missing calibration parameter file raises PolicyConfigurationError and never silently falls back."""
    missing_path = tmp_path / "nonexistent_params.json"
    with pytest.raises(PolicyConfigurationError, match="Calibrated policy parameters file not found"):
        load_calibrated_params(params_path=missing_path, force_reload=True)

    with patch("sentinelai.triage.decision_engine.CALIBRATED_PARAMS_PATH", missing_path):
        pred = {"class_id": 0, "class_label": "Benign", "probabilities": {0: 0.90, 4: 0.10}}
        with pytest.raises(PolicyConfigurationError):
            evaluate_triage_decision(pred, two_stage_mode=True)


def test_malformed_json_fails_clearly(tmp_path):
    """Malformed JSON in calibration file raises PolicyConfigurationError."""
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text("{this is not json", encoding="utf-8")
    with pytest.raises(PolicyConfigurationError, match="Malformed JSON in calibration file"):
        load_calibrated_params(params_path=bad_json_path, force_reload=True)


def test_missing_required_keys_fails_clearly(tmp_path):
    """Missing required top-level keys raises PolicyConfigurationError."""
    # Missing selected_thresholds
    p1 = tmp_path / "missing_thresh.json"
    p1.write_text(json.dumps({"class_reliability": {}, "high_confusion_classes": []}), encoding="utf-8")
    with pytest.raises(PolicyConfigurationError, match="Missing required key 'selected_thresholds'"):
        load_calibrated_params(params_path=p1, force_reload=True)

    # Missing class_reliability
    p2 = tmp_path / "missing_rel.json"
    p2.write_text(json.dumps({"selected_thresholds": {"theta_low": 0.2, "theta_high": 0.7}}), encoding="utf-8")
    with pytest.raises(PolicyConfigurationError, match="Missing required key 'class_reliability'"):
        load_calibrated_params(params_path=p2, force_reload=True)

    # Missing class in class_reliability
    p3 = tmp_path / "incomplete_rel.json"
    p3.write_text(json.dumps({
        "selected_thresholds": {"theta_low": 0.2, "theta_high": 0.7},
        "class_reliability": {"0": 0.98},  # Missing classes 1..9
        "high_confusion_classes": [1],
    }), encoding="utf-8")
    with pytest.raises(PolicyConfigurationError, match="Missing reliability score for class 1"):
        load_calibrated_params(params_path=p3, force_reload=True)


def test_invalid_threshold_ranges_fail_clearly(tmp_path):
    """Invalid threshold ranges (ordering or bounds) raise PolicyConfigurationError."""
    # theta_low >= theta_high
    p1 = tmp_path / "inverted_thresholds.json"
    p1.write_text(json.dumps({
        "selected_thresholds": {"theta_low": 0.8, "theta_high": 0.3},
        "class_reliability": {str(i): 0.5 for i in range(10)},
        "high_confusion_classes": [1],
    }), encoding="utf-8")
    with pytest.raises(PolicyConfigurationError, match="Invalid threshold ordering"):
        load_calibrated_params(params_path=p1, force_reload=True)

    # theta_high > 1.0
    p2 = tmp_path / "out_of_bounds.json"
    p2.write_text(json.dumps({
        "selected_thresholds": {"theta_low": 0.2, "theta_high": 1.5},
        "class_reliability": {str(i): 0.5 for i in range(10)},
        "high_confusion_classes": [1],
    }), encoding="utf-8")
    with pytest.raises(PolicyConfigurationError, match="out of bounds"):
        load_calibrated_params(params_path=p2, force_reload=True)


def test_model_policy_pairing_handling():
    """Model-policy pairing is checked and explicit operational evidence is added."""
    pred = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.10, 4: 0.85, 3: 0.05},
    }

    # 1. Fresh model + fresh two-stage policy (intended evaluated pairing)
    dec_fresh = evaluate_triage_decision(pred, two_stage_mode=True, model_version="fresh")
    assert dec_fresh.policy_mode == "two_stage_experimental"
    assert any("Validated configuration: fresh model paired with fresh validation-calibrated" in e for e in dec_fresh.evidence)
    assert not any("Unvalidated pairing" in u for u in dec_fresh.uncertainty_reasons)

    # 2. Legacy model + fresh two-stage policy (cross-version pairing)
    dec_legacy = evaluate_triage_decision(pred, two_stage_mode=True, model_version="legacy")
    assert dec_legacy.policy_mode == "two_stage_experimental"
    assert any("Operational warning" in e for e in dec_legacy.evidence)
    assert any("Unvalidated pairing" in u for u in dec_legacy.uncertainty_reasons)


def test_confidence_calculation_uses_fresh_reliability_in_experimental_mode():
    """Experimental mode calculates confidence with validation reliability (e.g. 0.22 vs legacy 0.35)."""
    # Class 1 (Analysis)
    pred_analysis = {
        "class_id": 1,
        "class_label": "Analysis",
        "probabilities": {1: 0.70, 0: 0.20, 4: 0.10},
    }
    # Legacy mode uses legacy reliability 0.35
    # top_score=0.70, margin=0.50, rel=0.35 -> 0.40*0.70 + 0.35*0.50 + 0.25*0.35 = 0.28 + 0.175 + 0.0875 = 0.5425 -> 0.542 (round-to-even)
    dec_leg = evaluate_triage_decision(pred_analysis, two_stage_mode=False)
    assert dec_leg.decision_confidence == 0.542

    # Experimental mode uses fresh validation reliability 0.22
    # top_score=0.70, margin=0.50, rel=0.22 -> 0.40*0.70 + 0.35*0.50 + 0.25*0.22 = 0.28 + 0.175 + 0.055 = 0.510
    dec_exp = evaluate_triage_decision(pred_analysis, two_stage_mode=True, model_version="fresh")
    assert dec_exp.decision_confidence == 0.510
    assert dec_exp.decision_confidence < dec_leg.decision_confidence


def test_historical_record_backward_compatibility():
    """Historical records without policy_mode deserialize cleanly with policy_mode=None."""
    dec = TriageDecision(
        predicted_class="Benign",
        priority=AlertPriority.LOW,
        recommended_action="allow_and_standard_monitoring",
        decision_confidence=0.88,
        decision_status=DecisionStatus.ACCEPTED,
        requires_human_review=False,
    )
    assert dec.policy_mode is None
    dumped = dec.model_dump()
    assert dumped["policy_mode"] is None
