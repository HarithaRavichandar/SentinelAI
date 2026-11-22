"""SQLite persistence layer for SentinelAI alert history.

This module provides lightweight, zero-dependency persistence for triage results
using the Python standard library sqlite3 module. It stores predicted classes,
vote probabilities, decision metadata, and latency metrics while strictly omitting
raw network payload features for security and privacy.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentinelai.storage")

# Default database location under the project data/ directory
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "alerts.db"


def get_db_path() -> Path:
    """Return the configured SQLite database file path."""
    custom = os.getenv("SENTINELAI_DB_PATH")
    if custom:
        return Path(custom)
    return _DEFAULT_DB_PATH


def get_db_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Create and configure a SQLite connection.

    Enables WAL mode and busy timeout for concurrent read/write safety.
    """
    target = Path(db_path) if db_path else get_db_path()
    if target != Path(":memory:"):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("Failed to create db parent directory: %s", exc)

    conn = sqlite3.connect(str(target), timeout=10.0)
    conn.row_factory = sqlite3.Row

    # Performance and concurrency optimizations
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
    except sqlite3.Error as exc:
        logger.debug("Failed to set PRAGMA (e.g. in-memory db): %s", exc)

    return conn


def _extract_str(val: Any) -> Optional[str]:
    """Helper to safely extract string values from enums or plain values."""
    if val is None:
        return None
    if hasattr(val, "value"):
        return str(val.value)
    s = str(val)
    if "." in s and ("AlertPriority" in s or "DecisionStatus" in s or "RecommendedAction" in s):
        return s.split(".")[-1].lower()
    return s


def init_db(db_path: Optional[Path | str] = None) -> None:
    """Initialize the alerts database table and indexes if they do not exist."""
    try:
        conn = get_db_connection(db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        class_id INTEGER NOT NULL,
                        class_label TEXT NOT NULL,
                        probabilities_json TEXT NOT NULL,
                        latency_ms REAL,
                        priority TEXT,
                        decision_status TEXT,
                        recommended_action TEXT,
                        decision_confidence REAL,
                        requires_human_review INTEGER,
                        decision_json TEXT,
                        explanation TEXT,
                        explanation_source TEXT,
                        alert_status TEXT DEFAULT 'new',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts (timestamp DESC);"
                )
                # Migration: add alert_status column to existing databases
                # This is safe to run repeatedly — it silently fails if column exists
                try:
                    conn.execute(
                        "ALTER TABLE alerts ADD COLUMN alert_status TEXT DEFAULT 'new';"
                    )
                except sqlite3.OperationalError:
                    pass  # Column already exists
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Database error during init_db: %s", exc)


def insert_alert(
    *,
    class_id: int,
    class_label: str,
    probabilities: Dict[str | int, float],
    latency_ms: Optional[float] = None,
    decision: Optional[Dict[str, Any]] = None,
    explanation: Optional[str] = None,
    explanation_source: Optional[str] = None,
    timestamp: Optional[int] = None,
    db_path: Optional[Path | str] = None,
) -> Optional[int]:
    """Persist a single triage alert into the database.

    Raw 76 network flow features are never stored. Returns the new record ID,
    or None if insertion failed.
    """
    try:
        if timestamp is None:
            timestamp = int(time.time() * 1000)

        # Serialize probabilities with string keys
        probs_clean: Dict[str, float] = {}
        if isinstance(probabilities, dict):
            for k, v in probabilities.items():
                try:
                    probs_clean[str(k)] = float(v)
                except (ValueError, TypeError):
                    continue
        probabilities_json = json.dumps(probs_clean)

        # Extract decision fields if available
        priority: Optional[str] = None
        decision_status: Optional[str] = None
        recommended_action: Optional[str] = None
        decision_confidence: Optional[float] = None
        requires_human_review_int: Optional[int] = None
        decision_json: Optional[str] = None

        if isinstance(decision, dict):
            priority = _extract_str(decision.get("priority"))
            decision_status = _extract_str(decision.get("decision_status"))
            recommended_action = _extract_str(decision.get("recommended_action"))

            raw_conf = decision.get("decision_confidence")
            if raw_conf is not None:
                try:
                    decision_confidence = float(raw_conf)
                except (ValueError, TypeError):
                    decision_confidence = None

            raw_review = decision.get("requires_human_review")
            if raw_review is not None:
                requires_human_review_int = 1 if bool(raw_review) else 0

            # Prepare decision dict for JSON serialization with serialized enums
            decision_serializable = {}
            for k, v in decision.items():
                if hasattr(v, "value"):
                    decision_serializable[k] = v.value
                else:
                    decision_serializable[k] = v

            try:
                decision_json = json.dumps(decision_serializable)
            except Exception:
                decision_json = None

        conn = get_db_connection(db_path)
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO alerts (
                        timestamp, class_id, class_label, probabilities_json,
                        latency_ms, priority, decision_status, recommended_action,
                        decision_confidence, requires_human_review, decision_json,
                        explanation, explanation_source, alert_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                    """,
                    (
                        timestamp,
                        int(class_id),
                        str(class_label),
                        probabilities_json,
                        float(latency_ms) if latency_ms is not None else None,
                        priority,
                        decision_status,
                        recommended_action,
                        decision_confidence,
                        requires_human_review_int,
                        decision_json,
                        str(explanation) if explanation is not None else None,
                        str(explanation_source) if explanation_source is not None else None,
                    ),
                )
                return cursor.lastrowid
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Database error persisting alert: %s", exc)
        return None


def update_alert_status(
    alert_id: int,
    alert_status: str,
    db_path: Optional[Path | str] = None,
) -> bool:
    """Update the workflow status of an alert. Returns True if the row was updated."""
    valid_statuses = {"new", "acknowledged", "investigating", "resolved", "false_positive"}
    if alert_status not in valid_statuses:
        raise ValueError(f"Invalid alert_status '{alert_status}'. Must be one of {valid_statuses}")

    try:
        conn = get_db_connection(db_path)
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE alerts SET alert_status = ? WHERE id = ?",
                    (alert_status, alert_id),
                )
                return cursor.rowcount > 0
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Database error updating alert status: %s", exc)
        return False


def get_alerts(
    limit: int = 50,
    db_path: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve recent alerts in descending chronological order.

    Returns an empty list on database errors or empty table.
    """
    safe_limit = max(1, min(int(limit), 500))
    try:
        init_db(db_path)
        conn = get_db_connection(db_path)
    except Exception as exc:
        logger.warning("Database connection error fetching alerts: %s", exc)
        return []

    try:
        cursor = conn.execute(
            """
            SELECT
                id, timestamp, class_id, class_label, probabilities_json,
                latency_ms, priority, decision_status, recommended_action,
                decision_confidence, requires_human_review, decision_json,
                explanation, explanation_source, alert_status
            FROM alerts
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        )
        rows = cursor.fetchall()
        alerts: List[Dict[str, Any]] = []
        for r in rows:
            # Parse probabilities
            try:
                probs = json.loads(r["probabilities_json"])
            except Exception:
                probs = {}

            # Parse full decision metadata if present
            decision_obj = None
            if r["decision_json"]:
                try:
                    decision_obj = json.loads(r["decision_json"])
                except Exception:
                    decision_obj = None

            # Map boolean requires_human_review
            review_flag: Optional[bool] = None
            if r["requires_human_review"] is not None:
                review_flag = bool(r["requires_human_review"])

            # Policy mode provenance: extract from decision_obj if explicitly recorded;
            # Never assume legacy for historical records where provenance is unrecorded.
            policy_mode: Optional[str] = None
            if isinstance(decision_obj, dict):
                policy_mode = decision_obj.get("policy_mode")

            record: Dict[str, Any] = {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "class_id": r["class_id"],
                "class_label": r["class_label"],
                "probabilities": probs,
                "latencyMs": r["latency_ms"],
                "priority": r["priority"],
                "decision_status": r["decision_status"],
                "recommended_action": r["recommended_action"],
                "decision_confidence": r["decision_confidence"],
                "requires_human_review": review_flag,
                "policy_mode": policy_mode,
                "alert_status": r["alert_status"] or "new",
            }

            if decision_obj:
                record["decision"] = decision_obj
            elif r["priority"] is not None or r["decision_status"] is not None:
                record["decision"] = {
                    "priority": r["priority"],
                    "decision_status": r["decision_status"],
                    "recommended_action": r["recommended_action"],
                    "decision_confidence": r["decision_confidence"],
                    "requires_human_review": review_flag,
                    "policy_mode": None,
                }

            if r["explanation"]:
                record["explanation"] = r["explanation"]
            if r["explanation_source"]:
                record["explanation_source"] = r["explanation_source"]

            alerts.append(record)
        return alerts
    except sqlite3.Error as exc:
        logger.warning("Database error fetching alerts: %s", exc)
        return []
    finally:
        conn.close()