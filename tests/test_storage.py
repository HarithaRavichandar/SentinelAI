"""Unit tests for the SentinelAI SQLite persistence layer."""

import json
import sqlite3
import pytest
from pathlib import Path
from sentinelai.storage.db import get_alerts, get_db_connection, init_db, insert_alert


@pytest.fixture
def temp_db(tmp_path: Path):
    """Provide an isolated temporary SQLite database."""
    db_file = tmp_path / "test_alerts.db"
    init_db(db_file)
    return db_file


def test_init_db_creates_table_and_index(temp_db: Path):
    """Verify table schema and indexes are created properly."""
    conn = get_db_connection(temp_db)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts';")
    assert cursor.fetchone() is not None

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_alerts_timestamp';")
    assert cursor.fetchone() is not None
    conn.close()


def test_insert_and_retrieve_alert_with_metadata(temp_db: Path):
    """Verify persisting and retrieving an alert with complete decision metadata."""
    decision = {
        "predicted_class": "Exploits",
        "priority": "critical",
        "decision_status": "accepted",
        "recommended_action": "escalate_to_soc_lead",
        "decision_confidence": 0.942,
        "requires_human_review": True,
        "evidence": ["High confidence match"],
    }
    probs = {"0": 0.02, "4": 0.94, "5": 0.04}

    alert_id = insert_alert(
        class_id=4,
        class_label="Exploits",
        probabilities=probs,
        latency_ms=125.4,
        decision=decision,
        explanation="Detected exploit behavior.",
        explanation_source="groq",
        timestamp=1730000000000,
        db_path=temp_db,
    )

    assert alert_id is not None
    assert alert_id > 0

    alerts = get_alerts(limit=10, db_path=temp_db)
    assert len(alerts) == 1
    record = alerts[0]

    assert record["id"] == alert_id
    assert record["timestamp"] == 1730000000000
    assert record["class_id"] == 4
    assert record["class_label"] == "Exploits"
    assert record["probabilities"]["4"] == pytest.approx(0.94)
    assert record["priority"] == "critical"
    assert record["decision_status"] == "accepted"
    assert record["recommended_action"] == "escalate_to_soc_lead"
    assert record["decision_confidence"] == pytest.approx(0.942)
    assert record["requires_human_review"] is True
    assert record["decision"]["priority"] == "critical"
    assert record["explanation"] == "Detected exploit behavior."
    assert record["explanation_source"] == "groq"


def test_insert_and_retrieve_legacy_alert_without_decision(temp_db: Path):
    """Verify compatibility with older records that omit decision metadata."""
    alert_id = insert_alert(
        class_id=0,
        class_label="Benign",
        probabilities={"0": 0.99, "1": 0.01},
        timestamp=1720000000000,
        db_path=temp_db,
    )

    assert alert_id is not None
    alerts = get_alerts(limit=5, db_path=temp_db)
    assert len(alerts) == 1
    record = alerts[0]

    assert record["class_label"] == "Benign"
    assert record["priority"] is None
    assert record["decision_status"] is None
    assert record["recommended_action"] is None
    assert record["decision_confidence"] is None
    assert record["requires_human_review"] is None
    # decision dictionary should be None or empty
    assert record.get("decision") is None


def test_retrieval_deterministic_ordering_and_limit(temp_db: Path):
    """Verify ordering is strictly descending by timestamp, then id."""
    for i in range(5):
        insert_alert(
            class_id=i,
            class_label=f"Class_{i}",
            probabilities={str(i): 1.0},
            timestamp=1000 + i * 100,
            db_path=temp_db,
        )

    # Request limit of 3
    results = get_alerts(limit=3, db_path=temp_db)
    assert len(results) == 3

    timestamps = [r["timestamp"] for r in results]
    assert timestamps == [1400, 1300, 1200]
    assert results[0]["class_label"] == "Class_4"


def test_database_error_handling_non_crashing(tmp_path: Path):
    """Verify that database errors do not crash the application."""
    # Invalid directory path
    invalid_path = tmp_path / "non_existent_subdir" / "cannot_create"
    # Make a file where directory should be to force sqlite error
    invalid_path.parent.write_text("blocking file")

    res = insert_alert(
        class_id=0,
        class_label="Benign",
        probabilities={"0": 1.0},
        db_path=invalid_path / "test.db",
    )
    assert res is None  # Handled safely, returned None

    alerts = get_alerts(limit=10, db_path=invalid_path / "test.db")
    assert alerts == []  # Handled safely, returned empty list


def test_privacy_no_raw_features_stored(temp_db: Path):
    """Verify table schema has no columns for raw features."""
    conn = get_db_connection(temp_db)
    cursor = conn.execute("PRAGMA table_info(alerts);")
    columns = [row["name"] for row in cursor.fetchall()]
    conn.close()

    forbidden = ["payload", "raw_features", "Flow Duration", "Total Fwd Packet", "features"]
    for col in forbidden:
        assert col not in columns


def test_storage_preserves_policy_mode(temp_db: Path):
    """Verify persisting and retrieving alerts preserves policy_mode in decision_json."""
    decision_legacy = {
        "predicted_class": "Benign",
        "priority": "low",
        "decision_status": "accepted",
        "recommended_action": "allow_and_standard_monitoring",
        "decision_confidence": 0.95,
        "requires_human_review": False,
        "policy_mode": "legacy",
    }
    id_legacy = insert_alert(
        class_id=0,
        class_label="Benign",
        probabilities={"0": 0.95},
        decision=decision_legacy,
        timestamp=1730000000000,
        db_path=temp_db,
    )

    decision_exp = {
        "predicted_class": "Exploits",
        "priority": "medium",
        "decision_status": "review_required",
        "recommended_action": "inspect_uncertain_traffic_and_review",
        "decision_confidence": 0.65,
        "requires_human_review": True,
        "policy_mode": "two_stage_experimental",
    }
    id_exp = insert_alert(
        class_id=4,
        class_label="Exploits",
        probabilities={"0": 0.50, "4": 0.50},
        decision=decision_exp,
        timestamp=1730000001000,
        db_path=temp_db,
    )

    alerts = get_alerts(limit=10, db_path=temp_db)
    assert len(alerts) == 2

    exp_rec = next(a for a in alerts if a["id"] == id_exp)
    assert exp_rec["policy_mode"] == "two_stage_experimental"
    assert exp_rec["decision"]["policy_mode"] == "two_stage_experimental"

    legacy_rec = next(a for a in alerts if a["id"] == id_legacy)
    assert legacy_rec["policy_mode"] == "legacy"
    assert legacy_rec["decision"]["policy_mode"] == "legacy"


def test_storage_historical_alerts_without_policy_mode_report_none(temp_db: Path):
    """Historical records without policy_mode in decision_json report None (unknown, not assumed legacy)."""
    conn = get_db_connection(temp_db)
    # Simulate an alert inserted by an older version of SentinelAI
    old_decision_json = json.dumps({
        "predicted_class": "Exploits",
        "priority": "critical",
        "decision_status": "accepted",
        "recommended_action": "isolate_workstation_and_open_incident",
        "decision_confidence": 0.90,
        "requires_human_review": True,
        # 'policy_mode' is intentionally absent in historical records
    })
    with conn:
        conn.execute(
            """
            INSERT INTO alerts (
                timestamp, class_id, class_label, probabilities_json,
                priority, decision_status, recommended_action,
                decision_confidence, requires_human_review, decision_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1710000000000, 4, "Exploits", json.dumps({"4": 0.90}),
                "critical", "accepted", "isolate_workstation_and_open_incident",
                0.90, 1, old_decision_json,
            ),
        )
    conn.close()

    alerts = get_alerts(limit=5, db_path=temp_db)
    assert len(alerts) == 1
    record = alerts[0]
    assert record["priority"] == "critical"
    # Provenance was not recorded, so it must be None (unknown), never assumed legacy
    assert record["policy_mode"] is None
    assert record["decision"].get("policy_mode") is None

