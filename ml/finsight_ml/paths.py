from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "shared"
FIXTURES = SHARED / "fixtures"
ML = REPO / "ml"
DATA = ML / "data"
REAL = DATA / "real"  # gitignored: the team's own labelled, masked messages
REPORTS = ML / "reports"
MODELS = REPO / "backend" / "models" / "classifier"
APP_ASSETS = REPO / "app" / "assets"
