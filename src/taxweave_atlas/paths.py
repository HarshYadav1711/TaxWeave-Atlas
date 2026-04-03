from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root (contains reference_pack/, templates/)."""
    return Path(__file__).resolve().parents[2]


def reference_pack_dir() -> Path:
    return project_root() / "reference_pack"


def templates_dir() -> Path:
    return project_root() / "templates"
