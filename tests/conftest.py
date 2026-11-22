# tests/conftest.py
"""Test configuration to ensure the project's ``src`` directory is on ``sys.path``.
This enables imports like ``import sentinelai`` in test modules without installing the package.
"""
import sys
from pathlib import Path
import pytest

# Add the repository's src directory (two levels up from this file) to the import path.
repo_root = Path(__file__).resolve().parents[1]
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


@pytest.fixture(autouse=True)
def clean_test_env(monkeypatch):
    """Ensure tests run in clean baseline environment unless explicitly overridden."""
    monkeypatch.delenv("SENTINELAI_TWO_STAGE_TRIAGE", raising=False)

