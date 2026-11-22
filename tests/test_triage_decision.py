# tests/test_triage_decision.py
"""Tests for confidence-aware cybersecurity alert triage decision engine (Laya)."""

import pytest
from fastapi.testclient import TestClient

from sentinelai.api import app
from sentinelai.triage.decision_engine import (
    AlertPriority,
    DecisionStatus,
    TriageDecision,
    compute_decision_confidence,
    evaluate_triage_decision,
    is_two_stage_enabled,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_decision_env(monkeypatch):
    """Ensure clean feature flag environment and cache reset for decision engine tests."""
    monkeypatch.delenv("SENTINELAI_TWO_STAGE_TRIAGE", raising=False)
    import sentinelai.triage.decision_engine as de
    de._CACHED_CALIBRATED_PARAMS = None
    yield
    de._CACHED_CALIBRATED_PARAMS = None


def test_triage_decision_pydantic_contract():
    """Verify TriageDecision Pydantic contract validation."""
    decision = TriageDecision(
        predicted_class="Benign",
        priority=AlertPriority.LOW,
        recommended_action="allow_and_standard_monitoring",
        decision_confidence=0.85,
        decision_status=DecisionStatus.ACCEPTED,
        evidence=["High confidence benign flow."],
        uncertainty_reasons=[],
        requires_human_review=False,
    )
    dumped = decision.model_dump()
    assert dumped["predicted_class"] == "Benign"
    assert dumped["priority"] == "low"
    assert dumped["decision_status"] == "accepted"
    assert dumped["requires_human_review"] is False

    # Out of bounds confidence should raise ValidationError
    with pytest.raises(Exception):
        TriageDecision(
            predicted_class="Benign",
            priority=AlertPriority.LOW,
            recommended_action="allow",
            decision_confidence=1.5,  # > 1.0
            decision_status=DecisionStatus.ACCEPTED,
            requires_human_review=False,
        )


def test_benign_high_confidence_accepted():
    """Benign flow with clear margin is accepted with low priority and standard monitoring."""
    prediction = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.90, 4: 0.05, 3: 0.05},
    }
    decision = evaluate_triage_decision(prediction)
    assert decision.predicted_class == "Benign"
    assert decision.priority == AlertPriority.LOW
    assert decision.decision_status == DecisionStatus.ACCEPTED
    assert decision.requires_human_review is False
    assert decision.recommended_action == "allow_and_standard_monitoring"
    assert decision.decision_confidence > 0.70


def test_benign_narrow_margin_requires_review():
    """Benign flow with narrow margin triggers human review."""
    prediction = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.45, 4: 0.40, 3: 0.15},
    }
    decision = evaluate_triage_decision(prediction)
    assert decision.priority == AlertPriority.MEDIUM
    assert decision.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision.requires_human_review is True
    assert any("Narrow score margin" in r for r in decision.uncertainty_reasons)


def test_critical_attack_exploits_escalation():
    """Exploits prediction with high confidence assigns Critical priority and isolation."""
    prediction = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {4: 0.88, 0: 0.08, 3: 0.04},
    }
    decision = evaluate_triage_decision(prediction)
    assert decision.predicted_class == "Exploits"
    assert decision.priority == AlertPriority.CRITICAL
    assert decision.recommended_action == "isolate_workstation_and_open_incident"
    # Destructive actions require human analyst review before execution
    assert decision.requires_human_review is True


def test_high_attack_dos_recommendation():
    """DoS prediction recommends non-destructive rate-limiting."""
    prediction = {
        "class_id": 3,
        "class_label": "DoS",
        "probabilities": {3: 0.85, 0: 0.10, 4: 0.05},
    }
    decision = evaluate_triage_decision(prediction)
    assert decision.predicted_class == "DoS"
    assert decision.priority in {AlertPriority.HIGH, AlertPriority.MEDIUM}
    assert "rate_limiting" in decision.recommended_action or "connection_pool" in decision.recommended_action


def test_high_confusion_classes_force_review():
    """Shellcode (ID 8) and Analysis (ID 1) always enforce human review due to low validation precision."""
    shellcode_pred = {
        "class_id": 8,
        "class_label": "Shellcode",
        "probabilities": {8: 0.95, 0: 0.05},
    }
    decision = evaluate_triage_decision(shellcode_pred)
    assert decision.priority == AlertPriority.HIGH
    assert decision.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision.requires_human_review is True
    assert any("low empirical precision" in r for r in decision.uncertainty_reasons)

    analysis_pred = {
        "class_id": 1,
        "class_label": "Analysis",
        "probabilities": {1: 0.80, 0: 0.20},
    }
    decision_ana = evaluate_triage_decision(analysis_pred)
    assert decision_ana.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision_ana.requires_human_review is True


def test_conflicting_evidence_argmax_mismatch():
    """If predicted class_id contradicts argmax of probabilities, flag review_required."""
    prediction = {
        "class_id": 0,  # Benign
        "class_label": "Benign",
        "probabilities": {0: 0.20, 4: 0.80},  # Argmax is Exploits (4)
    }
    decision = evaluate_triage_decision(prediction)
    assert decision.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision.requires_human_review is True
    assert any("Conflicting evidence" in r for r in decision.uncertainty_reasons)


def test_low_or_invalid_confidence_distribution():
    """Empty or non-finite probabilities distribution triggers review_required."""
    prediction = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {},
    }
    decision = evaluate_triage_decision(prediction)
    assert decision.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision.requires_human_review is True
    assert any("empty or zero" in r for r in decision.uncertainty_reasons)


def test_missing_or_malformed_input():
    """Missing class_id or invalid payload returns unavailable status safely."""
    decision_none = evaluate_triage_decision(None)  # type: ignore
    assert decision_none.decision_status == DecisionStatus.UNAVAILABLE
    assert decision_none.priority == AlertPriority.REVIEW_REQUIRED
    assert decision_none.requires_human_review is True

    decision_empty = evaluate_triage_decision({})
    assert decision_empty.decision_status == DecisionStatus.UNAVAILABLE
    assert decision_empty.requires_human_review is True


def test_shap_evidence_inclusion():
    """Positive SHAP features are summarized into evidence list without claiming malicious intent."""
    prediction = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {4: 0.80, 0: 0.10, 3: 0.10},
    }
    shap_data = {
        "sbytes": 0.32,
        "dbytes": 0.18,
        "sttl": 0.45,
        "sloss": -0.15,
        "dloss": -0.12,
        "sload": -0.14,
    }
    decision = evaluate_triage_decision(prediction, shap_result=shap_data)
    assert any("sttl (+0.450)" in e for e in decision.evidence)
    # Attribution note must explicitly state it does not prove malicious intent
    assert any("do not constitute proof of malicious intent" in e for e in decision.evidence)
    # 3 opposing features should be noted
    assert any("opposing SHAP features" in r for r in decision.uncertainty_reasons)


def test_abnormal_or_weak_score_distribution():
    """Scores that sum abnormally or have very weak top score trigger review_required."""
    # Abnormal sum (< 0.50)
    abnormal_pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.10, 4: 0.05},
    }
    decision_ab = evaluate_triage_decision(abnormal_pred)
    assert decision_ab.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision_ab.requires_human_review is True
    assert any("Abnormal score distribution sum" in r for r in decision_ab.uncertainty_reasons)

    # Weak top score (< 0.30) even if normalized
    weak_pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.25, 1: 0.20, 2: 0.15, 3: 0.15, 4: 0.15, 5: 0.10},
    }
    decision_weak = evaluate_triage_decision(weak_pred)
    assert decision_weak.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision_weak.requires_human_review is True
    assert any("Low top model score" in r for r in decision_weak.uncertainty_reasons)



def test_triage_api_backward_compatibility_and_decision(client):
    """Verify that /triage returns existing keys and adds structured decision."""
    # Build 76 zero features
    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine()
    features = {col: 0.0 for col in engine.columns}

    response = client.post("/triage", json=features)
    assert response.status_code == 200
    data = response.json()

    # Legacy keys preserved
    assert "class_id" in data
    assert "class_label" in data
    assert "probabilities" in data
    assert "explanation" in data
    assert "explanation_source" in data

    # Structured decision added
    assert "decision" in data
    dec = data["decision"]
    assert "predicted_class" in dec
    assert "priority" in dec
    assert "recommended_action" in dec
    assert "decision_confidence" in dec
    assert "decision_status" in dec
    assert "evidence" in dec
    assert "uncertainty_reasons" in dec
    assert "requires_human_review" in dec
    assert isinstance(dec["evidence"], list)
    assert isinstance(dec["requires_human_review"], bool)


def test_direct_decision_endpoint(client):
    """Verify /decision endpoint returns the structured decision directly."""
    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine()
    features = {col: 0.0 for col in engine.columns}

    response = client.post("/decision", json=features)
    assert response.status_code == 200
    dec = response.json()
    assert "predicted_class" in dec
    assert "priority" in dec
    assert "recommended_action" in dec
    assert "decision_confidence" in dec
    assert "decision_status" in dec
    assert "requires_human_review" in dec


def test_triage_independent_of_llm_failure(client, monkeypatch):
    """Verify that if LLM provider fails, decision engine still works reliably."""
    def fake_get_explanation(*args, **kwargs):
        raise RuntimeError("LLM connection timeout")

    monkeypatch.setattr("sentinelai.api.get_explanation", fake_get_explanation)

    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine()
    features = {col: 0.0 for col in engine.columns}

    response = client.post("/triage", json=features)
    assert response.status_code == 200
    data = response.json()
    assert data["explanation_source"] in ("template", "placeholder")
    assert "decision" in data
    assert data["decision"]["decision_status"] in {"accepted", "review_required"}


# =========================================================================
# Two-Stage Triage Policy Feature Flag & Threshold Boundary Tests
# =========================================================================

def test_two_stage_flag_disabled_by_default():
    """Verify that the two-stage feature flag is off by default."""
    from sentinelai.triage.decision_engine import is_two_stage_enabled
    # Default without explicit env setting is False
    assert is_two_stage_enabled() is False

    # Standard benign prediction in default mode runs legacy evaluation
    pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.85, 4: 0.15},
    }
    decision = evaluate_triage_decision(pred)
    assert not any("Two-stage triage policy active" in e for e in decision.evidence)


def test_two_stage_legacy_mode_preserved():
    """Verify that when two_stage_mode=False, legacy decision behavior is strictly preserved."""
    # Narrow margin benign triggers review in legacy mode
    pred_narrow = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.45, 4: 0.40, 3: 0.15},
    }
    dec_legacy = evaluate_triage_decision(pred_narrow, two_stage_mode=False)
    assert dec_legacy.priority == AlertPriority.MEDIUM
    assert dec_legacy.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_legacy.requires_human_review is True
    assert not any("Two-stage triage policy active" in e for e in dec_legacy.evidence)


def test_two_stage_zone1_auto_benign_sub_20():
    """p_attack < 0.20: benign candidate, low priority, accepted, standard monitoring."""
    pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.85, 4: 0.10, 3: 0.05},  # p_attack = 0.15
    }
    decision = evaluate_triage_decision(pred, two_stage_mode=True)
    assert decision.priority == AlertPriority.LOW
    assert decision.decision_status == DecisionStatus.ACCEPTED
    assert decision.requires_human_review is False
    assert decision.recommended_action == "allow_and_standard_monitoring"
    assert any("p_attack=0.150 (< 0.20 threshold)" in e for e in decision.evidence)


def test_two_stage_threshold_boundary_20():
    """Verify exact threshold boundary at 0.20 (Zone 1 vs Zone 2)."""
    # 0.199 -> Zone 1 (Auto-Benign)
    pred_under = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.801, 4: 0.199},  # p_attack = 0.199
    }
    dec_under = evaluate_triage_decision(pred_under, two_stage_mode=True)
    assert dec_under.priority == AlertPriority.LOW
    assert dec_under.decision_status == DecisionStatus.ACCEPTED
    assert dec_under.requires_human_review is False

    # 0.200 -> Zone 2 (Review band: review_required, requires_human_review=True, medium priority)
    pred_exact = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.800, 4: 0.200},  # p_attack = 0.200
    }
    dec_exact = evaluate_triage_decision(pred_exact, two_stage_mode=True)
    assert dec_exact.priority == AlertPriority.MEDIUM
    assert dec_exact.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_exact.requires_human_review is True
    assert dec_exact.recommended_action == "inspect_uncertain_traffic_and_review"
    assert any("falls in uncertainty review band" in e for e in dec_exact.evidence)


def test_two_stage_zone2_review_band_medium_priority():
    """0.30 <= p_attack < 0.70: review_required, requires_human_review=True, medium priority."""
    pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.50, 4: 0.40, 5: 0.10},  # p_attack = 0.50
    }
    decision = evaluate_triage_decision(pred, two_stage_mode=True)
    assert decision.priority == AlertPriority.MEDIUM
    assert decision.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert decision.requires_human_review is True
    assert decision.recommended_action == "inspect_uncertain_traffic_and_review"
    # Verify critical/high priority is NOT assigned solely because review is required
    assert decision.priority not in {AlertPriority.CRITICAL, AlertPriority.HIGH}


def test_two_stage_threshold_boundary_70():
    """Verify exact threshold boundary at 0.70 (Zone 2 vs Zone 3)."""
    # 0.699 -> Zone 2 (Review band: MEDIUM priority, inspect_uncertain_traffic_and_review)
    pred_under = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.301, 4: 0.699},  # p_attack = 0.699
    }
    dec_under = evaluate_triage_decision(pred_under, two_stage_mode=True)
    assert dec_under.priority == AlertPriority.MEDIUM
    assert dec_under.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_under.requires_human_review is True
    assert dec_under.recommended_action == "inspect_uncertain_traffic_and_review"

    # 0.700 -> Zone 3 (Stage 2 Threat-Tier Evaluation)
    pred_exact = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.300, 4: 0.700},  # p_attack = 0.700
    }
    dec_exact = evaluate_triage_decision(pred_exact, two_stage_mode=True)
    # Zone 3 advances to Stage 2 threat-tier: Exploits with moderate confidence gets HIGH priority quarantine
    assert dec_exact.priority == AlertPriority.HIGH
    assert dec_exact.recommended_action == "quarantine_traffic_and_escalate"
    assert any("Advancing to Stage 2 threat-tier" in e for e in dec_exact.evidence)


def test_two_stage_zone3_threat_tier_escalation():
    """p_attack >= 0.70: retains predicted class and applies existing threat-tier safeguards."""
    # Critical threat (Exploits)
    pred_exploits = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {4: 0.85, 0: 0.10, 3: 0.05},  # p_attack = 0.90
    }
    dec_exp = evaluate_triage_decision(pred_exploits, two_stage_mode=True)
    assert dec_exp.predicted_class == "Exploits"
    assert dec_exp.priority == AlertPriority.CRITICAL
    assert dec_exp.requires_human_review is True  # Critical sign-off required

    # High threat (DoS)
    pred_dos = {
        "class_id": 3,
        "class_label": "DoS",
        "probabilities": {3: 0.85, 0: 0.10, 4: 0.05},  # p_attack = 0.90
    }
    dec_dos = evaluate_triage_decision(pred_dos, two_stage_mode=True)
    assert dec_dos.predicted_class == "DoS"
    assert dec_dos.priority == AlertPriority.HIGH


def test_two_stage_zone3_low_reliability_classes_enforce_review():
    """Low-reliability classes in Zone 3 enforce human review and review_required status."""
    shellcode_pred = {
        "class_id": 8,
        "class_label": "Shellcode",
        "probabilities": {8: 0.80, 0: 0.20},  # p_attack = 0.80 >= 0.70
    }
    dec_sc = evaluate_triage_decision(shellcode_pred, two_stage_mode=True)
    assert dec_sc.predicted_class == "Shellcode"
    assert dec_sc.priority == AlertPriority.HIGH
    assert dec_sc.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_sc.requires_human_review is True

    analysis_pred = {
        "class_id": 1,
        "class_label": "Analysis",
        "probabilities": {1: 0.75, 0: 0.25},  # p_attack = 0.75 >= 0.70
    }
    dec_ana = evaluate_triage_decision(analysis_pred, two_stage_mode=True)
    assert dec_ana.predicted_class == "Analysis"
    assert dec_ana.priority == AlertPriority.MEDIUM
    assert dec_ana.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_ana.requires_human_review is True


def test_two_stage_invalid_and_missing_scores_handled_safely():
    """Invalid, missing, or non-finite scores are never silently treated as benign."""
    # 1. Missing class 0
    missing_pred = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {4: 0.85, 3: 0.15},
    }
    dec_missing = evaluate_triage_decision(missing_pred, two_stage_mode=True)
    assert dec_missing.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_missing.requires_human_review is True
    assert any("Class 0 (Benign) score is missing" in r for r in dec_missing.uncertainty_reasons)

    # 2. Empty probabilities
    empty_pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {},
    }
    dec_empty = evaluate_triage_decision(empty_pred, two_stage_mode=True)
    assert dec_empty.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_empty.requires_human_review is True

    # 3. Non-finite score
    nan_pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: float("nan"), 4: 0.50},
    }
    dec_nan = evaluate_triage_decision(nan_pred, two_stage_mode=True)
    assert dec_nan.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_nan.requires_human_review is True

    # 4. Negative score
    neg_pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: -0.10, 4: 1.10},
    }
    dec_neg = evaluate_triage_decision(neg_pred, two_stage_mode=True)
    assert dec_neg.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_neg.requires_human_review is True

    # 5. Abnormal sum
    abnormal_pred = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.10, 4: 0.05},
    }
    dec_abn = evaluate_triage_decision(abnormal_pred, two_stage_mode=True)
    assert dec_abn.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_abn.requires_human_review is True


def test_two_stage_environment_flag_activation(client, monkeypatch):
    """Setting SENTINELAI_TWO_STAGE_TRIAGE=true activates two-stage triage via API."""
    monkeypatch.setenv("SENTINELAI_TWO_STAGE_TRIAGE", "true")

    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine()
    features = {col: 0.0 for col in engine.columns}

    response = client.post("/triage", json=features)
    assert response.status_code == 200
    data = response.json()
    assert "decision" in data
    dec = data["decision"]
    assert any("Two-stage triage policy active" in e for e in dec["evidence"])
    assert dec["policy_mode"] == "two_stage_experimental"


def test_default_feature_flag_is_off():
    """Verify SENTINELAI_TWO_STAGE_TRIAGE defaults to disabled (False)."""
    assert is_two_stage_enabled() is False


def test_legacy_decisions_report_legacy_provenance():
    """All decisions evaluated under legacy policy explicitly report policy_mode='legacy'."""
    # 1. Benign low
    pred_benign = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.90, 4: 0.05, 3: 0.05},
    }
    dec_benign = evaluate_triage_decision(pred_benign, two_stage_mode=False)
    assert dec_benign.policy_mode == "legacy"

    # 2. Critical Exploits
    pred_exploits = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {4: 0.88, 0: 0.08, 3: 0.04},
    }
    dec_exploits = evaluate_triage_decision(pred_exploits, two_stage_mode=False)
    assert dec_exploits.policy_mode == "legacy"

    # 3. Invalid prediction fallback
    dec_invalid = evaluate_triage_decision({}, two_stage_mode=False)
    assert dec_invalid.policy_mode == "legacy"


def test_experimental_decisions_report_two_stage_provenance():
    """All decisions evaluated under two-stage policy report policy_mode='two_stage_experimental'."""
    # 1. Stage 1 Benign Candidate (p_attack < 0.20)
    pred_low = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.85, 4: 0.10, 3: 0.05},
    }
    dec_low = evaluate_triage_decision(pred_low, two_stage_mode=True)
    assert dec_low.policy_mode == "two_stage_experimental"

    # 2. Stage 1 Review Band (0.30 <= p_attack < 0.70)
    pred_mid = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.50, 4: 0.35, 3: 0.15},
    }
    dec_mid = evaluate_triage_decision(pred_mid, two_stage_mode=True)
    assert dec_mid.policy_mode == "two_stage_experimental"

    # 3. Stage 2 Threat-Tier Escalation (p_attack >= 0.70)
    pred_high = {
        "class_id": 4,
        "class_label": "Exploits",
        "probabilities": {0: 0.10, 4: 0.85, 3: 0.05},
    }
    dec_high = evaluate_triage_decision(pred_high, two_stage_mode=True)
    assert dec_high.policy_mode == "two_stage_experimental"


def test_default_api_triage_reports_legacy_provenance(client):
    """By default (feature flag OFF), /triage and /decision report policy_mode='legacy'."""
    from sentinelai.inference import InferenceEngine
    engine = InferenceEngine()
    features = {col: 0.0 for col in engine.columns}

    res = client.post("/triage", json=features)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"]["policy_mode"] == "legacy"

    res_dec = client.post("/decision", json=features)
    assert res_dec.status_code == 200
    assert res_dec.json()["policy_mode"] == "legacy"


def test_triage_decision_backward_compatibility_none_policy_mode():
    """TriageDecision instantiated without policy_mode defaults to None (safe for historical deserialization)."""
    dec = TriageDecision(
        predicted_class="Benign",
        priority=AlertPriority.LOW,
        recommended_action="allow_and_standard_monitoring",
        decision_confidence=0.90,
        decision_status=DecisionStatus.ACCEPTED,
        requires_human_review=False,
    )
    assert dec.policy_mode is None
    dumped = dec.model_dump()
    assert dumped["policy_mode"] is None


def test_decision_status_accepted_and_review_required_contracts():
    """Verify contracts for both 'accepted' and 'review_required' decision statuses."""
    # 1. Accepted: Clear separation, meets confidence criteria, no human review needed
    benign_high_conf = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.95, 3: 0.03, 4: 0.02},
    }
    dec_accepted = evaluate_triage_decision(benign_high_conf)
    assert dec_accepted.decision_status == DecisionStatus.ACCEPTED
    assert dec_accepted.requires_human_review is False
    assert dec_accepted.priority == AlertPriority.LOW

    # 2. Review Required: Narrow margin / ambiguity enforces human analyst review
    benign_ambiguous = {
        "class_id": 0,
        "class_label": "Benign",
        "probabilities": {0: 0.40, 3: 0.35, 4: 0.25},
    }
    dec_review = evaluate_triage_decision(benign_ambiguous)
    assert dec_review.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_review.requires_human_review is True
    assert dec_review.priority == AlertPriority.MEDIUM


def test_shellcode_safeguard_forces_high_and_review_under_experimental_policy(monkeypatch):
    """Predicted class Shellcode (ID 8) must force HIGH priority and human review under experimental policy."""
    # Test directly with two_stage_mode=True
    shellcode_pred = {
        "class_id": 8,
        "class_label": "Shellcode",
        "probabilities": {8: 0.92, 0: 0.08},
    }
    dec = evaluate_triage_decision(shellcode_pred, two_stage_mode=True)
    assert dec.predicted_class == "Shellcode"
    assert dec.priority == AlertPriority.HIGH
    assert dec.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec.requires_human_review is True
    assert dec.recommended_action == "manual_deep_packet_inspection"

    # Test via environment flag SENTINELAI_TWO_STAGE_TRIAGE=true
    monkeypatch.setenv("SENTINELAI_TWO_STAGE_TRIAGE", "true")
    dec_env = evaluate_triage_decision(shellcode_pred)
    assert dec_env.predicted_class == "Shellcode"
    assert dec_env.priority == AlertPriority.HIGH
    assert dec_env.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert dec_env.requires_human_review is True
    assert dec_env.recommended_action == "manual_deep_packet_inspection"
    assert dec_env.policy_mode == "two_stage_experimental"



