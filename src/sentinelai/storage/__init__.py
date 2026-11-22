"""Storage package for SentinelAI."""

from sentinelai.storage.db import get_alerts, init_db, insert_alert

__all__ = ["get_alerts", "init_db", "insert_alert"]

