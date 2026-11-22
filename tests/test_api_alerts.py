"""Integration tests for the /alerts API endpoint and triage persistence."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sentinelai.api import app
from sentinelai.storage.db import init_db


@pytest.fixture
def client_with_temp_db(tmp_path: Path, monkeypatch):
    """Configure FastAPI client pointing to an isolated SQLite test database."""
    db_file = tmp_path / "test_api_alerts.db"
    init_db(db_file)
    monkeypatch.setenv("SENTINELAI_DB_PATH", str(db_file))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_payload():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "sample_features.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_get_alerts_initially_empty(client_with_temp_db: TestClient):
    """GET /alerts should return 200 with an empty list initially."""
    resp = client_with_temp_db.get("/alerts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_triage_persists_and_returns_id(client_with_temp_db: TestClient, sample_payload: dict):
    """POST /triage should persist the alert and return a record id."""
    triage_resp = client_with_temp_db.post("/triage", json=sample_payload)
    assert triage_resp.status_code == 200
    triage_data = triage_resp.json()

    assert "id" in triage_data
    assert isinstance(triage_data["id"], int)
    assert "decision" in triage_data
    assert "priority" in triage_data["decision"]

    # Now verify GET /alerts reflects this newly persisted alert
    alerts_resp = client_with_temp_db.get("/alerts")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert len(alerts) == 1

    stored = alerts[0]
    assert stored["id"] == triage_data["id"]
    assert stored["class_id"] == triage_data["class_id"]
    assert stored["class_label"] == triage_data["class_label"]
    assert stored["priority"] == triage_data["decision"]["priority"]
    assert stored["decision_status"] == triage_data["decision"]["decision_status"]
    assert stored["recommended_action"] == triage_data["decision"]["recommended_action"]
    assert stored["decision_confidence"] == pytest.approx(triage_data["decision"]["decision_confidence"])
    assert stored["requires_human_review"] == triage_data["decision"]["requires_human_review"]


def test_get_alerts_respects_limit(client_with_temp_db: TestClient, sample_payload: dict):
    """Verify limit parameter caps the returned records."""
    # Insert 3 records
    for _ in range(3):
        client_with_temp_db.post("/triage", json=sample_payload)

    resp_all = client_with_temp_db.get("/alerts?limit=10")
    assert len(resp_all.json()) == 3

    resp_limited = client_with_temp_db.get("/alerts?limit=2")
    assert len(resp_limited.json()) == 2


def test_triage_succeeds_even_if_db_fails(client_with_temp_db: TestClient, sample_payload: dict, monkeypatch):
    """Ensure failure in persistence does not cause /triage to fail."""
    def broken_insert(*args, **kwargs):
        raise RuntimeError("Disk full simulation")

    monkeypatch.setattr("sentinelai.api.insert_alert", broken_insert)

    resp = client_with_temp_db.post("/triage", json=sample_payload)
    assert resp.status_code == 200
    data = resp.json()
    # Triage succeeds with decision, even if DB write failed
    assert "class_id" in data
    assert "decision" in data

