"""
Verify an on-disk dataset folder matches the structure blueprint (strict set equality).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.structure.blueprint import (
    allowed_root_files,
    build_layout_context,
    expected_root_outer_names,
    expected_structure_directories,
    iter_layout_file_specs,
    load_structure_blueprint,
)


def validate_dataset_structure(
    dataset_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """
    Return error messages (empty if the tree matches the blueprint).
    When ``manifest`` is set, format, token, and ``files_sha256`` digests are verified.
    """
    errors: list[str] = []
    dataset_dir = dataset_dir.resolve()
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
            errors.append("manifest format must be taxweave-atlas-dataset-files-v2")
        mv = manifest.get("structure_blueprint_version")
        if mv != bp_version:
            errors.append(
                f"structure_blueprint_version mismatch manifest={mv!r} spec={bp_version!r}"
            )
        if manifest.get("export_token") != token:
            errors.append(
                f"export_token mismatch manifest={manifest.get('export_token')!r} expected={token!r}"
            )

    allowed = allowed_root_files()
    outers_expected = set(
        expected_root_outer_names(
            case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
        )
    )

    if not dataset_dir.is_dir():
        return [f"dataset directory missing: {dataset_dir}"]

    root_dirs = {p.name for p in dataset_dir.iterdir() if p.is_dir()}
    root_files = {p.name for p in dataset_dir.iterdir() if p.is_file()}

    if root_dirs != outers_expected:
        errors.append(
            "root folder set mismatch: "
            f"got {sorted(root_dirs)} expected {sorted(outers_expected)}"
        )

    extra_root_files = root_files - allowed
    if extra_root_files:
        errors.append(f"unexpected root files: {sorted(extra_root_files)}")
    for must in ("case.json", "questionnaire.json", "00_dataset_files_manifest.json"):
        if must not in root_files:
            errors.append(f"missing required root file {must!r}")

    all_dirs: set[str] = set()
    actual_contract_files: set[str] = set()
    for p in dataset_dir.rglob("*"):
        rel = p.relative_to(dataset_dir).as_posix()
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
            f"directory set mismatch: extra={extra_d[:25]} missing={miss_d[:25]}"
        )

    if actual_contract_files != expected_files:
        missing = sorted(expected_files - actual_contract_files)
        extra = sorted(actual_contract_files - expected_files)
        if missing:
            errors.append(f"missing contract files: {missing[:25]}")
        if extra:
            errors.append(f"extra contract files: {extra[:25]}")

    if errors:
        return errors

    if manifest is not None:
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            errors.append("manifest missing files_sha256 map")
            return errors
        if set(fmap.keys()) != expected_files:
            errors.append("manifest files_sha256 keys do not match expected contract paths")
            return errors
        for rel, exp_hash in fmap.items():
            fp = dataset_dir.joinpath(*str(rel).split("/"))
            if not fp.is_file():
                errors.append(f"manifest lists missing path {rel!r}")
                continue
            got = hashlib.sha256(fp.read_bytes()).hexdigest()
            if got != exp_hash:
                errors.append(f"checksum mismatch for {rel!r}")

    return errors


def load_manifest_dict(dataset_dir: Path) -> dict[str, Any] | None:
    p = dataset_dir / "00_dataset_files_manifest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


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
