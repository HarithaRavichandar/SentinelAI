# tests/conftest.py
"""Test configuration to ensure the project's ``src`` directory is on ``sys.path``.
This enables imports like ``import sentinelai`` in test modules without installing the package.
"""
import sys
from pathlib import Path

# Add the repository's src directory (two levels up from this file) to the import path.
repo_root = Path(__file__).resolve().parents[1]
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
