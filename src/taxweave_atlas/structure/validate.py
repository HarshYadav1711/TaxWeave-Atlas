"""
Verify staging and export dataset folders against the structure blueprint (strict set equality).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.structure.blueprint import (
    build_layout_context,
    expected_export_root_outer_names,
    expected_root_outer_names,
    expected_structure_directories,
    export_allowed_root_files,
    iter_export_layout_file_specs,
    iter_layout_file_specs,
    load_structure_blueprint,
    staging_allowed_root_files,
)
from taxweave_atlas.structure.layout import EXPORT_MANIFEST_FILENAME, EXPORT_MANIFEST_FORMAT


def validate_staging_dataset_structure(
    staging_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """
    Return error messages (empty if the staging tree matches the full blueprint).
    """
    errors: list[str] = []
    staging_dir = staging_dir.resolve()
    specs = iter_layout_file_specs(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    expected_files = {rel for rel, _ in specs}
    expected_dirs = expected_structure_directories(sorted(expected_files))

    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    token = ctx["export_token"]
    bp_version = load_structure_blueprint().get("version")

    if manifest is not None:
        if manifest.get("format") != "taxweave-atlas-dataset-files-v2":
            errors.append("staging manifest format must be taxweave-atlas-dataset-files-v2")
        mv = manifest.get("structure_blueprint_version")
        if mv != bp_version:
            errors.append(
                f"structure_blueprint_version mismatch manifest={mv!r} spec={bp_version!r}"
            )
        if manifest.get("export_token") != token:
            errors.append(
                f"export_token mismatch manifest={manifest.get('export_token')!r} expected={token!r}"
            )

    allowed = staging_allowed_root_files()
    outers_expected = set(
        expected_root_outer_names(
            case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
        )
    )

    if not staging_dir.is_dir():
        return [f"staging directory missing: {staging_dir}"]

    root_dirs = {p.name for p in staging_dir.iterdir() if p.is_dir()}
    root_files = {p.name for p in staging_dir.iterdir() if p.is_file()}

    if root_dirs != outers_expected:
        errors.append(
            "staging root folder set mismatch: "
            f"got {sorted(root_dirs)} expected {sorted(outers_expected)}"
        )

    extra_root_files = root_files - allowed
    if extra_root_files:
        errors.append(f"unexpected staging root files: {sorted(extra_root_files)}")
    for must in sorted(allowed):
        if must not in root_files:
            errors.append(f"missing required staging root file {must!r}")

    all_dirs: set[str] = set()
    actual_contract_files: set[str] = set()
    for p in staging_dir.rglob("*"):
        rel = p.relative_to(staging_dir).as_posix()
        if p.is_dir():
            if rel != ".":
                all_dirs.add(rel)
        elif p.is_file():
            if rel not in allowed:
                actual_contract_files.add(rel)

    if all_dirs != expected_dirs:
        extra_d = sorted(all_dirs - expected_dirs)
        miss_d = sorted(expected_dirs - all_dirs)
        errors.append(
            f"staging directory set mismatch: extra={extra_d[:25]} missing={miss_d[:25]}"
        )

    if actual_contract_files != expected_files:
        missing = sorted(expected_files - actual_contract_files)
        extra = sorted(actual_contract_files - expected_files)
        if missing:
            errors.append(f"missing staging contract files: {missing[:25]}")
        if extra:
            errors.append(f"extra staging contract files: {extra[:25]}")

    if errors:
        return errors

    if manifest is not None:
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            errors.append("staging manifest missing files_sha256 map")
            return errors
        if set(fmap.keys()) != expected_files:
            errors.append("staging manifest files_sha256 keys do not match expected contract paths")
            return errors
        for rel, exp_hash in fmap.items():
            fp = staging_dir.joinpath(*str(rel).split("/"))
            if not fp.is_file():
                errors.append(f"staging manifest lists missing path {rel!r}")
                continue
            got = hashlib.sha256(fp.read_bytes()).hexdigest()
            if got != exp_hash:
                errors.append(f"staging checksum mismatch for {rel!r}")

    return errors


def validate_export_dataset_structure(
    export_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """
    PDF-only deliverable tree: root contains only ``manifest.json``; all nested files are ``.pdf``.
    """
    errors: list[str] = []
    export_dir = export_dir.resolve()
    specs = iter_export_layout_file_specs(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    expected_files = {rel for rel, _ in specs}
    expected_dirs = expected_structure_directories(sorted(expected_files))

    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    token = ctx["export_token"]
    bp_version = load_structure_blueprint().get("version")

    if manifest is not None:
        if manifest.get("format") != EXPORT_MANIFEST_FORMAT:
            errors.append(f"export manifest format must be {EXPORT_MANIFEST_FORMAT!r}")
        mv = manifest.get("structure_blueprint_version")
        if mv != bp_version:
            errors.append(
                f"structure_blueprint_version mismatch export manifest={mv!r} spec={bp_version!r}"
            )
        if manifest.get("export_token") != token:
            errors.append(
                f"export_token mismatch manifest={manifest.get('export_token')!r} expected={token!r}"
            )

    allowed_root = export_allowed_root_files()
    outers_expected = set(
        expected_export_root_outer_names(
            case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
        )
    )

    if not export_dir.is_dir():
        return [f"export directory missing: {export_dir}"]

    root_dirs = {p.name for p in export_dir.iterdir() if p.is_dir()}
    root_files = {p.name for p in export_dir.iterdir() if p.is_file()}

    if root_dirs != outers_expected:
        errors.append(
            "export root folder set mismatch: "
            f"got {sorted(root_dirs)} expected {sorted(outers_expected)}"
        )

    extra_root_files = root_files - allowed_root
    if extra_root_files:
        errors.append(f"unexpected export root files (PDF-only deliverables): {sorted(extra_root_files)}")
    for must in sorted(allowed_root):
        if must not in root_files:
            errors.append(f"missing required export root file {must!r}")

    all_dirs: set[str] = set()
    actual_contract_files: set[str] = set()
    for p in export_dir.rglob("*"):
        rel = p.relative_to(export_dir).as_posix()
        if p.is_dir():
            if rel != ".":
                all_dirs.add(rel)
        elif p.is_file():
            if rel == EXPORT_MANIFEST_FILENAME:
                continue
            if rel not in allowed_root:
                actual_contract_files.add(rel)
            lower = p.name.lower()
            if lower != EXPORT_MANIFEST_FILENAME.lower() and not lower.endswith(".pdf"):
                errors.append(f"non-PDF file in export tree: {rel!r}")

    if all_dirs != expected_dirs:
        extra_d = sorted(all_dirs - expected_dirs)
        miss_d = sorted(expected_dirs - all_dirs)
        errors.append(
            f"export directory set mismatch: extra={extra_d[:25]} missing={miss_d[:25]}"
        )

    if actual_contract_files != expected_files:
        missing = sorted(expected_files - actual_contract_files)
        extra = sorted(actual_contract_files - expected_files)
        if missing:
            errors.append(f"missing export contract files: {missing[:25]}")
        if extra:
            errors.append(f"extra export contract files: {extra[:25]}")

    if errors:
        return errors

    if manifest is not None:
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            errors.append("export manifest missing files_sha256 map")
            return errors
        if set(fmap.keys()) != expected_files:
            errors.append("export manifest files_sha256 keys do not match expected export paths")
            return errors
        for rel, exp_hash in fmap.items():
            fp = export_dir.joinpath(*str(rel).split("/"))
            if not fp.is_file():
                errors.append(f"export manifest lists missing path {rel!r}")
                continue
            got = hashlib.sha256(fp.read_bytes()).hexdigest()
            if got != exp_hash:
                errors.append(f"export checksum mismatch for {rel!r}")

    return errors


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
