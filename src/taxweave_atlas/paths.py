from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root: the directory that contains ``config/``, ``specs/``, and ``src/``."""
    return Path(__file__).resolve().parents[2]


def specs_dir() -> Path:
    return project_root() / "specs"


def sample_pack_dir() -> Path:
    return specs_dir() / "sample_pack"


def templates_spec_dir() -> Path:
    return specs_dir() / "templates"


def dataset_structure_blueprint_path() -> Path:
    return specs_dir() / "dataset_structure_blueprint.yaml"


def structure_blueprint_path() -> Path:
    return specs_dir() / "dataset_structure_blueprint.yaml"


def config_dir() -> Path:
    return project_root() / "config"


def generator_config_dir() -> Path:
    return config_dir() / "generator"


def staging_datasets_root(batch_output_root: Path) -> Path:
    """Internal build tree: JSON, DOCX, XLSX, XML, staging manifest (not shipped as deliverables)."""
    return batch_output_root / "_staging" / "datasets"
