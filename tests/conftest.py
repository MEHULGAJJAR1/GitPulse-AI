"""Shared test setup: make the backend, ELT and ML packages importable from any test folder."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "backend", ROOT / "data_pipeline"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
