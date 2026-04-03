"""
Strict ``dataset_structure_blueprint.yaml`` contract: scored checks, manifest order, naming.

A dataset passes only when ``blueprint_compliance_score_percent == 100.0`` (all checks green).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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


@dataclass
class BlueprintComplianceReport:
    """Per-tree audit against the blueprint; 100% required for delivery success."""

    tree: str  # "staging" | "export"
    check_results: list[tuple[str, bool, str]] = field(default_factory=list)

    def record(self, check_id: str, ok: bool, detail: str = "") -> None:
        self.check_results.append((check_id, ok, detail))

    @property
    def checks_passed(self) -> int:
        return sum(1 for _, ok, _ in self.check_results if ok)

    @property
    def checks_total(self) -> int:
        return len(self.check_results)

    @property
    def score_percent(self) -> float:
        if self.checks_total == 0:
            return 100.0
        return round(100.0 * self.checks_passed / self.checks_total, 4)

    @property
    def is_full_compliance(self) -> bool:
        return self.checks_total > 0 and self.checks_passed == self.checks_total

    def failure_messages(self) -> list[str]:
        out: list[str] = []
        for cid, ok, detail in self.check_results:
            if ok:
                continue
            msg = f"[blueprint:{self.tree}:{cid}] {detail}" if detail else f"[blueprint:{self.tree}:{cid}] failed"
            out.append(msg)
        return out

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "tree": self.tree,
            "checks_total": self.checks_total,
            "checks_passed": self.checks_passed,
            "score_percent": self.score_percent,
            "full_compliance": self.is_full_compliance,
            "checks": [
                {"id": cid, "ok": ok, "detail": detail or None}
                for cid, ok, detail in self.check_results
            ],
        }


def _run_check(
    report: BlueprintComplianceReport,
    check_id: str,
    fn: Callable[[], tuple[bool, str]],
) -> None:
    ok, detail = fn()
    report.record(check_id, ok, detail)


def audit_staging_blueprint_compliance(
    staging_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None,
) -> BlueprintComplianceReport:
    report = BlueprintComplianceReport(tree="staging")
    staging_dir = staging_dir.resolve()
    bp = load_structure_blueprint()
    bp_version = bp.get("version")
    specs = iter_layout_file_specs(case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt)
    expected_paths_ordered = [rel for rel, _ in specs]
    expected_files = set(expected_paths_ordered)
    expected_dirs = expected_structure_directories(expected_paths_ordered)
    ctx = build_layout_context(case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt)
    token = ctx["export_token"]
    allowed_root = staging_allowed_root_files()
    outers_ordered = expected_root_outer_names(case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt)
    outers_set = set(outers_ordered)

    def chk_dir_exists() -> tuple[bool, str]:
        if staging_dir.is_dir():
            return True, ""
        return False, f"staging directory missing or not a directory: {staging_dir}"

    def chk_root_files_exact() -> tuple[bool, str]:
        if not staging_dir.is_dir():
            return False, "skip"
        names = {p.name for p in staging_dir.iterdir() if p.is_file()}
        if names != allowed_root:
            return (
                False,
                f"staging root files must match blueprint exactly: got {sorted(names)} "
                f"expected {sorted(allowed_root)}",
            )
        return True, ""

    def chk_root_segment_dirs_set() -> tuple[bool, str]:
        if not staging_dir.is_dir():
            return False, "skip"
        dirs = {p.name for p in staging_dir.iterdir() if p.is_dir()}
        if dirs != outers_set:
            return (
                False,
                f"segment root folder set mismatch: got {sorted(dirs)} expected {sorted(outers_set)}",
            )
        return True, ""

    def chk_root_segment_blueprint_order() -> tuple[bool, str]:
        """Order actual folder names by blueprint segment index; must equal blueprint list."""
        if not staging_dir.is_dir():
            return False, "skip"
        actual = [p.name for p in staging_dir.iterdir() if p.is_dir()]
        if set(actual) != outers_set:
            return True, ""  # covered by set check
        try:
            ordered_actual = sorted(actual, key=lambda n: outers_ordered.index(n))
        except ValueError as e:
            return False, f"unexpected segment root folder name not in blueprint: {e}"
        if ordered_actual != outers_ordered:
            return (
                False,
                "segment root folders must follow blueprint segment order when canonically sorted "
                f"by blueprint index: expected {outers_ordered!r} got {ordered_actual!r}",
            )
        return True, ""

    def chk_export_token_in_outer_names() -> tuple[bool, str]:
        for name in outers_ordered:
            if token not in name:
                return (
                    False,
                    f"segment outer folder {name!r} must contain export_token {token!r} per blueprint template",
                )
        return True, ""

    def chk_inner_folder_segment() -> tuple[bool, str]:
        """Each contract path is ``{outer}/{inner}/…``; ``inner`` must match that segment's inner_template."""
        for rel in expected_files:
            parts = rel.split("/")
            if len(parts) < 3:
                return False, f"contract path must be outer/inner/leaf, got {rel!r}"
            outer = parts[0]
            inner_actual = parts[1]
            matched = False
            for seg in bp["segments"]:
                o = str(seg["outer_template"]).format(**ctx)
                if o != outer:
                    continue
                inner_exp = str(seg["inner_template"]).format(**ctx)
                if inner_actual != inner_exp:
                    return (
                        False,
                        f"path {rel!r}: inner folder {inner_actual!r} != blueprint inner {inner_exp!r} "
                        f"for segment {seg.get('id')!r}",
                    )
                matched = True
                break
            if not matched:
                return False, f"path {rel!r}: outer folder {outer!r} does not match any segment outer_template"
        return True, ""

    def chk_directory_hierarchy() -> tuple[bool, str]:
        if not staging_dir.is_dir():
            return False, "skip"
        all_dirs: set[str] = set()
        for p in staging_dir.rglob("*"):
            rel = p.relative_to(staging_dir).as_posix()
            if p.is_dir() and rel != ".":
                all_dirs.add(rel)
        if all_dirs != expected_dirs:
            extra = sorted(all_dirs - expected_dirs)[:20]
            miss = sorted(expected_dirs - all_dirs)[:20]
            return False, f"folder hierarchy mismatch extra={extra} missing={miss}"
        return True, ""

    def chk_contract_files_only() -> tuple[bool, str]:
        if not staging_dir.is_dir():
            return False, "skip"
        actual_contract: set[str] = set()
        for p in staging_dir.rglob("*"):
            rel = p.relative_to(staging_dir).as_posix()
            if p.is_file() and rel not in allowed_root:
                actual_contract.add(rel)
        if actual_contract != expected_files:
            miss = sorted(expected_files - actual_contract)[:20]
            extra = sorted(actual_contract - expected_files)[:20]
            return False, f"contract file set mismatch missing={miss} extra={extra}"
        return True, ""

    def chk_leaf_naming() -> tuple[bool, str]:
        """Basenames: no path traversal, no empty components."""
        for rel in expected_paths_ordered:
            if ".." in rel or rel.startswith("/"):
                return False, f"invalid path {rel!r}"
            parts = rel.split("/")
            if any(not p.strip() for p in parts):
                return False, f"path has empty segment {rel!r}"
            leaf = parts[-1]
            if re.search(r'[<>:"|?*\\]', leaf):
                return False, f"leaf filename has illegal characters: {rel!r}"
        return True, ""

    def chk_manifest_meta() -> tuple[bool, str]:
        if manifest is None:
            return False, "manifest dict is None"
        if manifest.get("format") != "taxweave-atlas-dataset-files-v2":
            return False, "format must be taxweave-atlas-dataset-files-v2"
        if manifest.get("structure_blueprint_version") != bp_version:
            return (
                False,
                f"structure_blueprint_version {manifest.get('structure_blueprint_version')!r} != {bp_version!r}",
            )
        if manifest.get("export_token") != token:
            return False, f"export_token mismatch got {manifest.get('export_token')!r} expected {token!r}"
        return True, ""

    def chk_manifest_key_order() -> tuple[bool, str]:
        if manifest is None:
            return False, "no manifest"
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            return False, "files_sha256 must be a dict preserving blueprint write order"
        keys = list(fmap.keys())
        if len(keys) != len(expected_paths_ordered):
            return (
                False,
                f"manifest file count {len(keys)} != blueprint contract {len(expected_paths_ordered)} "
                "(cannot skip or add documents vs blueprint)",
            )
        if keys != expected_paths_ordered:
            diff_at = next(
                (i for i, (a, b) in enumerate(zip(keys, expected_paths_ordered)) if a != b),
                None,
            )
            return (
                False,
                "manifest files_sha256 keys must match blueprint document iteration order exactly "
                f"(deviation at index {diff_at}: got {keys[diff_at]!r} expected {expected_paths_ordered[diff_at]!r})",
            )
        return True, ""

    def chk_manifest_checksums() -> tuple[bool, str]:
        if manifest is None:
            return False, "no manifest"
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            return False, "files_sha256 missing"
        for rel, exp_hash in fmap.items():
            fp = staging_dir.joinpath(*str(rel).split("/"))
            if not fp.is_file():
                return False, f"manifest lists path not on disk: {rel!r}"
            got = hashlib.sha256(fp.read_bytes()).hexdigest()
            if got != exp_hash:
                return False, f"checksum mismatch for {rel!r}"
        return True, ""

    _run_check(report, "STAGING_DIR_EXISTS", chk_dir_exists)
    _run_check(report, "STAGING_ROOT_FILES_EXACT", chk_root_files_exact)
    _run_check(report, "STAGING_SEGMENT_ROOTS_SET", chk_root_segment_dirs_set)
    _run_check(report, "STAGING_SEGMENT_ROOTS_BLUEPRINT_ORDER", chk_root_segment_blueprint_order)
    _run_check(report, "STAGING_EXPORT_TOKEN_IN_OUTERS", chk_export_token_in_outer_names)
    _run_check(report, "STAGING_INNER_FOLDERS_MATCH_TEMPLATES", chk_inner_folder_segment)
    _run_check(report, "STAGING_DIRECTORY_HIERARCHY_EXACT", chk_directory_hierarchy)
    _run_check(report, "STAGING_CONTRACT_FILES_EXACT", chk_contract_files_only)
    _run_check(report, "STAGING_LEAF_NAMING_RULES", chk_leaf_naming)
    if manifest is not None:
        _run_check(report, "STAGING_MANIFEST_METADATA", chk_manifest_meta)
        _run_check(report, "STAGING_MANIFEST_FILE_ORDER", chk_manifest_key_order)
        _run_check(report, "STAGING_MANIFEST_CHECKSUMS", chk_manifest_checksums)
    else:
        report.record("STAGING_MANIFEST_METADATA", False, "manifest is required for strict blueprint audit")
        report.record("STAGING_MANIFEST_FILE_ORDER", False, "manifest is required for strict blueprint audit")
        report.record("STAGING_MANIFEST_CHECKSUMS", False, "manifest is required for strict blueprint audit")

    return report


def audit_export_blueprint_compliance(
    export_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    manifest: dict[str, Any] | None,
) -> BlueprintComplianceReport:
    report = BlueprintComplianceReport(tree="export")
    export_dir = export_dir.resolve()
    bp = load_structure_blueprint()
    bp_version = bp.get("version")
    specs = iter_export_layout_file_specs(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    expected_paths_ordered = [rel for rel, _ in specs]
    expected_files = set(expected_paths_ordered)
    expected_dirs = expected_structure_directories(expected_paths_ordered)
    ctx = build_layout_context(case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt)
    token = ctx["export_token"]
    allowed_root = export_allowed_root_files()
    outers_ordered = expected_export_root_outer_names(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    outers_set = set(outers_ordered)

    def chk_dir_exists() -> tuple[bool, str]:
        if export_dir.is_dir():
            return True, ""
        return False, f"export directory missing: {export_dir}"

    def chk_root_files_exact() -> tuple[bool, str]:
        if not export_dir.is_dir():
            return False, "skip"
        names = {p.name for p in export_dir.iterdir() if p.is_file()}
        if names != allowed_root:
            return (
                False,
                f"export root files must be exactly {sorted(allowed_root)}; got {sorted(names)}",
            )
        return True, ""

    def chk_root_segment_dirs() -> tuple[bool, str]:
        if not export_dir.is_dir():
            return False, "skip"
        dirs = {p.name for p in export_dir.iterdir() if p.is_dir()}
        if dirs != outers_set:
            return False, f"export segment roots got {sorted(dirs)} expected {sorted(outers_set)}"
        return True, ""

    def chk_root_segment_order() -> tuple[bool, str]:
        if not export_dir.is_dir():
            return False, "skip"
        actual = [p.name for p in export_dir.iterdir() if p.is_dir()]
        if set(actual) != outers_set:
            return True, ""
        ordered_actual = sorted(actual, key=lambda n: outers_ordered.index(n))
        if ordered_actual != outers_ordered:
            return (
                False,
                f"export segment roots must follow blueprint order: expected {outers_ordered!r} got {ordered_actual!r}",
            )
        return True, ""

    def chk_export_token_in_outers() -> tuple[bool, str]:
        for name in outers_ordered:
            if token not in name:
                return False, f"outer folder {name!r} must contain export_token {token!r}"
        return True, ""

    def chk_pdf_only_leaves() -> tuple[bool, str]:
        if not export_dir.is_dir():
            return False, "skip"
        for p in export_dir.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(export_dir).as_posix()
            if rel == EXPORT_MANIFEST_FILENAME:
                continue
            if p.suffix.lower() != ".pdf":
                return False, f"export tree allows only PDF leaves (and manifest.json): {rel!r}"
        return True, ""

    def chk_hierarchy() -> tuple[bool, str]:
        if not export_dir.is_dir():
            return False, "skip"
        all_dirs: set[str] = set()
        for p in export_dir.rglob("*"):
            rel = p.relative_to(export_dir).as_posix()
            if p.is_dir() and rel != ".":
                all_dirs.add(rel)
        if all_dirs != expected_dirs:
            extra = sorted(all_dirs - expected_dirs)[:20]
            miss = sorted(expected_dirs - all_dirs)[:20]
            return False, f"export folder hierarchy mismatch extra={extra} missing={miss}"
        return True, ""

    def chk_files_exact() -> tuple[bool, str]:
        if not export_dir.is_dir():
            return False, "skip"
        actual: set[str] = set()
        for p in export_dir.rglob("*"):
            rel = p.relative_to(export_dir).as_posix()
            if p.is_file() and rel != EXPORT_MANIFEST_FILENAME:
                actual.add(rel)
        if actual != expected_files:
            miss = sorted(expected_files - actual)[:15]
            extra = sorted(actual - expected_files)[:15]
            return False, f"export PDF contract set mismatch missing={miss} extra={extra}"
        return True, ""

    def chk_inner_folder_segment() -> tuple[bool, str]:
        for rel in expected_files:
            parts = rel.split("/")
            if len(parts) < 3:
                return False, f"export path must be outer/inner/leaf: {rel!r}"
            outer = parts[0]
            inner_actual = parts[1]
            matched = False
            for seg in bp["segments"]:
                if seg.get("export", True) is False:
                    continue
                o = str(seg["outer_template"]).format(**ctx)
                if o != outer:
                    continue
                inner_exp = str(seg["inner_template"]).format(**ctx)
                if inner_actual != inner_exp:
                    return (
                        False,
                        f"export path {rel!r}: inner {inner_actual!r} != {inner_exp!r} for segment {seg.get('id')!r}",
                    )
                matched = True
                break
            if not matched:
                return False, f"export path {rel!r}: outer {outer!r} not in exported blueprint segments"
        return True, ""

    def chk_leaf_naming() -> tuple[bool, str]:
        for rel in expected_paths_ordered:
            if not rel.lower().endswith(".pdf"):
                return False, f"export contract path must be PDF: {rel!r}"
        return True, ""

    def chk_manifest_meta() -> tuple[bool, str]:
        if manifest is None:
            return False, "manifest dict is None"
        if manifest.get("format") != EXPORT_MANIFEST_FORMAT:
            return False, f"format must be {EXPORT_MANIFEST_FORMAT!r}"
        if manifest.get("structure_blueprint_version") != bp_version:
            return (
                False,
                f"structure_blueprint_version {manifest.get('structure_blueprint_version')!r} != {bp_version!r}",
            )
        if manifest.get("export_token") != token:
            return False, "export_token mismatch"
        return True, ""

    def chk_manifest_key_order() -> tuple[bool, str]:
        if manifest is None:
            return False, "no manifest"
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            return False, "files_sha256 missing"
        keys = list(fmap.keys())
        if len(keys) != len(expected_paths_ordered):
            return (
                False,
                f"export manifest file count {len(keys)} != blueprint {len(expected_paths_ordered)}",
            )
        if keys != expected_paths_ordered:
            diff_at = next(
                (i for i, (a, b) in enumerate(zip(keys, expected_paths_ordered)) if a != b),
                None,
            )
            return (
                False,
                f"export manifest key order mismatch at {diff_at}: {keys[diff_at]!r} vs {expected_paths_ordered[diff_at]!r}",
            )
        return True, ""

    def chk_manifest_checksums() -> tuple[bool, str]:
        if manifest is None:
            return False, "no manifest"
        fmap = manifest.get("files_sha256")
        if not isinstance(fmap, dict):
            return False, "files_sha256 missing"
        for rel, exp_hash in fmap.items():
            fp = export_dir.joinpath(*str(rel).split("/"))
            if not fp.is_file():
                return False, f"missing file {rel!r}"
            got = hashlib.sha256(fp.read_bytes()).hexdigest()
            if got != exp_hash:
                return False, f"checksum mismatch {rel!r}"
        return True, ""

    _run_check(report, "EXPORT_DIR_EXISTS", chk_dir_exists)
    _run_check(report, "EXPORT_ROOT_FILES_EXACT", chk_root_files_exact)
    _run_check(report, "EXPORT_SEGMENT_ROOTS_SET", chk_root_segment_dirs)
    _run_check(report, "EXPORT_SEGMENT_ROOTS_BLUEPRINT_ORDER", chk_root_segment_order)
    _run_check(report, "EXPORT_TOKEN_IN_OUTERS", chk_export_token_in_outers)
    _run_check(report, "EXPORT_INNER_FOLDERS_MATCH_TEMPLATES", chk_inner_folder_segment)
    _run_check(report, "EXPORT_PDF_ONLY_DELIVERABLES", chk_pdf_only_leaves)
    _run_check(report, "EXPORT_DIRECTORY_HIERARCHY_EXACT", chk_hierarchy)
    _run_check(report, "EXPORT_CONTRACT_FILES_EXACT", chk_files_exact)
    _run_check(report, "EXPORT_LEAF_NAMING_PDF", chk_leaf_naming)
    if manifest is not None:
        _run_check(report, "EXPORT_MANIFEST_METADATA", chk_manifest_meta)
        _run_check(report, "EXPORT_MANIFEST_FILE_ORDER", chk_manifest_key_order)
        _run_check(report, "EXPORT_MANIFEST_CHECKSUMS", chk_manifest_checksums)
    else:
        report.record("EXPORT_MANIFEST_METADATA", False, "manifest required for strict blueprint audit")
        report.record("EXPORT_MANIFEST_FILE_ORDER", False, "manifest required for strict blueprint audit")
        report.record("EXPORT_MANIFEST_CHECKSUMS", False, "manifest required for strict blueprint audit")

    return report
