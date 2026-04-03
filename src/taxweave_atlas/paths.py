from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root (contains specs/, config/, src/)."""
    return Path(__file__).resolve().parents[2]


def specs_dir() -> Path:
    return project_root() / "specs"


def sample_pack_dir() -> Path:
    return specs_dir() / "sample_pack"


def templates_spec_dir() -> Path:
    return specs_dir() / "templates"


def config_dir() -> Path:
    return project_root() / "config"
