"""
Verify staging and export dataset folders against ``dataset_structure_blueprint.yaml``.

Validation is **strict contract** (not advisory): failures return actionable messages.
Full scoring lives in ``blueprint_compliance``; delivery requires 100%.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.structure.blueprint_compliance import (
    audit_export_blueprint_compliance,
    audit_staging_blueprint_compliance,
)
from taxweave_atlas.structure.layout import EXPORT_MANIFEST_FILENAME


def validate_staging_dataset_structure(
    staging_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """Return error messages (empty only on 100% blueprint compliance for staging)."""
    rep = audit_staging_blueprint_compliance(
        staging_dir,
        case,
        dataset_index=dataset_index,
        uniqueness_salt=uniqueness_salt,
        manifest=manifest,
    )
    return rep.failure_messages()


def validate_export_dataset_structure(
    export_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """Return error messages (empty only on 100% blueprint compliance for export)."""
    rep = audit_export_blueprint_compliance(
        export_dir,
        case,
        dataset_index=dataset_index,
        uniqueness_salt=uniqueness_salt,
        manifest=manifest,
    )
    return rep.failure_messages()


def load_staging_manifest_dict(staging_dir: Path) -> dict[str, Any] | None:
    p = staging_dir / "00_dataset_files_manifest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_export_manifest_dict(export_dir: Path) -> dict[str, Any] | None:
    p = export_dir / EXPORT_MANIFEST_FILENAME
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_manifest_dict(dataset_dir: Path) -> dict[str, Any] | None:
    """Prefer export ``manifest.json``; fall back to staging manifest for transitional paths."""
    ex = load_export_manifest_dict(dataset_dir)
    if ex is not None:
        return ex
    return load_staging_manifest_dict(dataset_dir)


def uniqueness_salt_for_slug(batch_root: Path, slug: str) -> int:
    """Read ``manifests/batch_plan.json`` when present; else 0."""
    from pydantic import ValidationError as PydanticValidationError

    from taxweave_atlas.orchestration.manifest import BatchPlan

    plan_path = batch_root / "manifests" / "batch_plan.json"
    if not plan_path.is_file():
        return 0
    try:
        plan = BatchPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except PydanticValidationError:
        return 0
    for d in plan.datasets:
        if d.slug == slug:
            return int(d.uniqueness_salt)
    return 0
