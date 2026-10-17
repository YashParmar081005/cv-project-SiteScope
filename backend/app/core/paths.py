"""Filesystem layout (overridable via environment variables)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", BACKEND_DIR.parent)).resolve()
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", BACKEND_DIR / "configs")).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data")).resolve()
REFERENCE_PHOTOS_DIR = Path(os.getenv("REFERENCE_PHOTOS_DIR", PROJECT_ROOT / "reference_photos")).resolve()
