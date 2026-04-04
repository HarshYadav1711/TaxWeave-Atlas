from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root: the directory that contains ``config/``, ``specs/``, and ``src/``."""
    return Path(__file__).resolve().parents[2]


def specs_dir() -> Path:
    return project_root() / "specs"


def sample_pack_dir() -> Path:
    return specs_dir() / "sample_pack"


def dataset_structure_blueprint_path() -> Path:
    return specs_dir() / "dataset_structure_blueprint.yaml"


def config_dir() -> Path:
    return project_root() / "config"


def generator_config_dir() -> Path:
    return config_dir() / "generator"


def irs_acroform_maps_path() -> Path:
    return specs_dir() / "irs_acroform_schedule_maps.yaml"


def irs_template_cache_dir() -> Path:
    """
    Downloaded IRS fillable PDFs (per tax year). Override with env ``TAXWEAVE_IRS_TEMPLATE_DIR``.
    """
    import os

    override = os.environ.get("TAXWEAVE_IRS_TEMPLATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return project_root() / "assets" / "irs_templates"


def staging_datasets_root(batch_output_root: Path) -> Path:
    """Internal build tree: JSON, DOCX, XLSX, XML, staging manifest (not shipped as deliverables)."""
    return batch_output_root / "_staging" / "datasets"
