"""
Post-generation checks for batch output trees.

Validates reconciled numeric coherence, filesystem completeness, strict dataset **structure**
from ``specs/dataset_structure_blueprint.yaml`` (manifest v2 + checksums), fingerprint uniqueness,
and (optionally) stratification against ``mix.yaml``.
Reports are written to ``manifests/delivery_validation_report.json`` and per-dataset
``manifests/delivery_audits/<slug>.json`` when enabled (deliverable ``datasets/`` stays PDF-only).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from taxweave_atlas.config_loader import load_generator_settings
from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.generation.uniqueness import case_fingerprint
from taxweave_atlas.orchestration.manifest import BatchPlan
from taxweave_atlas.pdf.pipeline import _parse_case_json_text
from taxweave_atlas.reconciliation.checks import validate_reconciled_case
from taxweave_atlas.paths import staging_datasets_root
from taxweave_atlas.reconciliation.paths_util import resolve_dotted_path
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.schema.questionnaire import QuestionnairePacket

log = logging.getLogger(__name__)

# Minimum paths that must exist and be non-null after reconciliation (JSON-shaped keys).
_COMPLETENESS_PATHS: tuple[str, ...] = (
    "tax_year",
    "profile.primary_first_name",
    "profile.primary_last_name",
    "profile.taxpayer_label",
    "profile.synthetic_ssn_primary",
    "profile.address.line1",
    "profile.address.city",
    "profile.address.zip",
    "income.wages",
    "income.w2.employer_ein",
    "income.forms_1099_int.payer_tin",
    "federal.lines.agi",
    "federal.lines.total_tax",
    "state.code",
    "state.tax_computed",
    "executive_summary.agi",
    "executive_summary.total_tax",
)


@dataclass
class DatasetAuditRecord:
    slug: str
    ok: bool
    case_fingerprint: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)
    blueprint_compliance: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchValidationReport:
    """Aggregate result of validating a batch output tree."""

    batch_root: Path
    ok: bool
    errors: list[str]
    warnings: list[str]
    dataset_count: int
    per_dataset: dict[str, DatasetAuditRecord]
    duplicate_fingerprints: list[str]

    def summary_line(self) -> str:
        status = "OK" if self.ok else "FAILED"
        return (
            f"delivery validation {status}: {self.dataset_count} dataset(s), "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


def _check_completeness(case: SyntheticTaxCase, rec: DatasetAuditRecord) -> None:
    data = case.model_dump(mode="json")
    for path in _COMPLETENESS_PATHS:
        try:
            v = resolve_dotted_path(data, path)
        except KeyError:
            rec.errors.append(f"completeness: missing {path}")
            continue
        if v is None:
            rec.errors.append(f"completeness: null {path}")
        elif isinstance(v, str) and v.strip() == "":
            rec.errors.append(f"completeness: empty string {path}")
    if not rec.errors:
        rec.checks_passed.append("field_completeness")


def _check_supporting_docs(case: SyntheticTaxCase, rec: DatasetAuditRecord) -> None:
    kinds = [d.kind for d in case.supporting_documents.documents]
    if kinds.count("w2") != 1:
        rec.errors.append(f"supporting docs: expected exactly one w2, got {kinds!r}")
    if kinds.count("1099_int") != 1:
        rec.errors.append(f"supporting docs: expected exactly one 1099_int, got {kinds!r}")
    div_expected = case.income.dividends_ordinary > 0
    has_div = "1099_div" in kinds
    if div_expected and not has_div:
        rec.errors.append("supporting docs: missing 1099_div while dividends_ordinary > 0")
    if not div_expected and has_div:
        rec.errors.append("supporting docs: unexpected 1099_div with zero dividends")
    if not rec.errors:
        rec.checks_passed.append("supporting_documents_shape")


def _verify_structure_contract(
    staging_folder: Path,
    export_folder: Path,
    case: SyntheticTaxCase,
    rec: DatasetAuditRecord,
    *,
    batch_root: Path,
    plan_by_slug: dict[str, Any],
) -> None:
    from taxweave_atlas.structure.blueprint import parse_dataset_slug_index
    from taxweave_atlas.structure.blueprint_compliance import (
        audit_export_blueprint_compliance,
        audit_staging_blueprint_compliance,
    )
    from taxweave_atlas.structure.validate import (
        load_export_manifest_dict,
        load_staging_manifest_dict,
        uniqueness_salt_for_slug,
    )

    errs_before = len(rec.errors)
    slug = staging_folder.name
    try:
        idx = parse_dataset_slug_index(slug)
    except ConfigurationError as e:
        rec.errors.append(str(e))
        return

    salt = int(plan_by_slug[slug].uniqueness_salt) if slug in plan_by_slug else uniqueness_salt_for_slug(
        batch_root, slug
    )

    man_staging = load_staging_manifest_dict(staging_folder)
    if man_staging is None:
        rec.errors.append("missing or unreadable staging 00_dataset_files_manifest.json")
        return

    st_rep = audit_staging_blueprint_compliance(
        staging_folder, case, dataset_index=idx, uniqueness_salt=salt, manifest=man_staging
    )
    rec.blueprint_compliance["staging"] = st_rep.to_audit_dict()
    for msg in st_rep.failure_messages():
        rec.errors.append(msg)
    if st_rep.is_full_compliance:
        rec.checks_passed.append("blueprint_staging_100")

    if not export_folder.is_dir():
        rec.errors.append(f"missing export folder {export_folder}")
    else:
        man_export = load_export_manifest_dict(export_folder)
        if man_export is None:
            rec.errors.append("missing or unreadable export manifest.json")
        else:
            ex_rep = audit_export_blueprint_compliance(
                export_folder, case, dataset_index=idx, uniqueness_salt=salt, manifest=man_export
            )
            rec.blueprint_compliance["export"] = ex_rep.to_audit_dict()
            for msg in ex_rep.failure_messages():
                rec.errors.append(msg)
            if ex_rep.is_full_compliance:
                rec.checks_passed.append("blueprint_export_100")

    if len(rec.errors) == errs_before:
        rec.checks_passed.append("output_integrity_structure")


def _verify_questionnaire_sidecar(folder: Path, case: SyntheticTaxCase, rec: DatasetAuditRecord) -> None:
    qpath = folder / "questionnaire.json"
    if not qpath.is_file():
        rec.errors.append("missing questionnaire.json")
        return
    try:
        q_raw = qpath.read_text(encoding="utf-8")
        q_disk = QuestionnairePacket.model_validate_json(q_raw)
    except (json.JSONDecodeError, PydanticValidationError) as e:
        rec.errors.append(f"invalid questionnaire.json: {e}")
        return
    if q_disk.model_dump(mode="json") != case.questionnaire.model_dump(mode="json"):
        rec.errors.append("questionnaire.json does not match case.questionnaire")
    else:
        rec.checks_passed.append("questionnaire_sidecar_match")


def _cross_form_numeric(case: SyntheticTaxCase, rec: DatasetAuditRecord) -> None:
    try:
        validate_reconciled_case(case)
    except Exception as e:
        rec.errors.append(f"cross-form / reconciliation checks: {e}")
    else:
        rec.checks_passed.append("cross_form_numeric")


def _write_dataset_audit(
    batch_root: Path,
    rec: DatasetAuditRecord,
    *,
    validated_at: str,
) -> None:
    payload = {
        "format": "taxweave-atlas-delivery-audit-v1",
        "validated_at_utc": validated_at,
        "slug": rec.slug,
        "case_fingerprint": rec.case_fingerprint,
        "ok": rec.ok,
        "checks_passed": rec.checks_passed,
        "errors": rec.errors,
        "warnings": rec.warnings,
        "blueprint_compliance": rec.blueprint_compliance,
    }
    audit_dir = batch_root / "manifests" / "delivery_audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / f"{rec.slug}.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _distribution_checks(
    n: int,
    cases: list[SyntheticTaxCase],
    *,
    strict: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if n == 0:
        return errors, warnings

    settings = load_generator_settings()
    strat = settings.get("stratification") or {}
    sw = strat.get("state_weights") or {}
    yw = strat.get("tax_year_weights") or {}
    cw = strat.get("complexity_weights") or {}

    states = [c.state.code for c in cases]
    years = [c.tax_year for c in cases]
    levels: list[str] = []
    for c in cases:
        cx = c.questionnaire.answers.extensions.get("complexity_tier")
        if cx is None or (isinstance(cx, str) and not str(cx).strip()):
            levels.append("__missing__")
        else:
            levels.append(str(cx))

    def _check_axis(
        label: str,
        observed: list[str | int],
        weights: dict[str, float],
    ) -> None:
        wkeys = {str(k): float(v) for k, v in weights.items()}
        total_w = sum(wkeys.values()) or 1.0
        norm = {k: v / total_w for k, v in wkeys.items()}
        counts = Counter(str(x) for x in observed)
        for k in norm:
            if k not in counts:
                counts[k] = 0
        for k, cnt in counts.items():
            if k not in norm:
                msg = f"distribution {label}: unexpected category {k!r} ({cnt} samples)"
                (errors if strict else warnings).append(msg)

        for k, p in norm.items():
            o = counts.get(k, 0)
            exp = n * p
            var = n * p * (1.0 - p)
            if var < 1e-12:
                continue
            if exp < 5.0:
                if o == 0 and n >= 30:
                    warnings.append(
                        f"distribution {label}: category {k!r} has zero samples "
                        f"(expected ~{exp:.1f}; small-sample noise possible)"
                    )
                continue
            z = abs(o - exp) / (var**0.5)
            if z > 3.0:
                msg = (
                    f"distribution {label}: category {k!r} count {o} vs expected ~{exp:.1f} "
                    f"(|z|≈{z:.2f})"
                )
                (errors if strict else warnings).append(msg)

    if isinstance(sw, dict) and sw:
        _check_axis("state", states, {str(k): float(v) for k, v in sw.items()})
    if isinstance(yw, dict) and yw:
        _check_axis("tax_year", years, {str(k): float(v) for k, v in yw.items()})
    if isinstance(cw, dict) and cw:
        _check_axis("complexity_tier", levels, {str(k): float(v) for k, v in cw.items()})

    return errors, warnings


def validate_batch_output(
    batch_root: Path,
    *,
    expect_pdfs: bool = True,
    strict_distribution: bool = False,
    write_per_dataset_audit: bool = True,
    write_batch_report: bool = True,
) -> BatchValidationReport:
    """
    Validate a generation output tree: internal ``_staging/datasets/dataset_XXXXX/`` (JSON + full
    artifacts) and PDF-only ``datasets/dataset_XXXXX/`` + ``manifest.json``, plus optional
    ``manifests/batch_plan.json``.

    Checks: duplicate fingerprints, field completeness, cross-form rules, staging + export structure,
    questionnaire sidecar match, strict PDF-only export, and (warning or strict error) mix.yaml.
    """
    batch_root = batch_root.resolve()
    staging_root = staging_datasets_root(batch_root)
    datasets_dir = batch_root / "datasets"

    validated_at = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []
    warnings: list[str] = []
    per_dataset: dict[str, DatasetAuditRecord] = {}

    plan_by_slug: dict[str, Any] = {}
    plan_path = batch_root / "manifests" / "batch_plan.json"
    if plan_path.is_file():
        try:
            plan = BatchPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
            plan_by_slug = {d.slug: d for d in plan.datasets}
        except PydanticValidationError as e:
            errors.append(f"invalid manifests/batch_plan.json: {e}")

    if not staging_root.is_dir():
        errors.append(f"Missing _staging/datasets/ under {batch_root}")

    case_paths = sorted(staging_root.glob("dataset_*/case.json")) if staging_root.is_dir() else []
    if not case_paths:
        errors.append("no _staging/datasets/dataset_*/case.json found")

    if expect_pdfs and not datasets_dir.is_dir():
        errors.append(f"Missing datasets/ under {batch_root} (PDF export root)")

    if plan_by_slug and len(case_paths) != len(plan_by_slug):
        errors.append(
            f"staging dataset folder count {len(case_paths)} != batch_plan.datasets {len(plan_by_slug)}"
        )

    all_fps: list[str] = []
    cases: list[SyntheticTaxCase] = []

    for cp in case_paths:
        staging_folder = cp.parent
        slug = staging_folder.name
        export_folder = datasets_dir / slug
        rec = DatasetAuditRecord(slug=slug, ok=False, case_fingerprint="")
        per_dataset[slug] = rec

        try:
            raw = cp.read_text(encoding="utf-8")
            case = _parse_case_json_text(raw)
        except (json.JSONDecodeError, PydanticValidationError) as e:
            rec.errors.append(f"case.json: {e}")
            if write_per_dataset_audit:
                _write_dataset_audit(batch_root, rec, validated_at=validated_at)
            continue

        cases.append(case)
        fp = case_fingerprint(case)
        rec.case_fingerprint = fp
        all_fps.append(fp)

        if slug in plan_by_slug:
            planned = plan_by_slug[slug]
            if planned.case_fingerprint and planned.case_fingerprint != fp:
                rec.errors.append(
                    f"fingerprint mismatch vs batch_plan: disk {fp!r} plan {planned.case_fingerprint!r}"
                )

        _cross_form_numeric(case, rec)
        _check_completeness(case, rec)
        _check_supporting_docs(case, rec)
        _verify_questionnaire_sidecar(staging_folder, case, rec)
        if expect_pdfs:
            _verify_structure_contract(
                staging_folder,
                export_folder,
                case,
                rec,
                batch_root=batch_root,
                plan_by_slug=plan_by_slug,
            )
        else:
            errs_before_json = len(rec.errors)
            for must in ("case.json", "questionnaire.json"):
                if not (staging_folder / must).is_file():
                    rec.errors.append(f"missing {must} under staging folder")
            if export_folder.is_dir() and any(export_folder.iterdir()):
                rec.errors.append(
                    f"export folder must be empty or absent when expect_pdfs=False: {export_folder}"
                )
            if len(rec.errors) == errs_before_json:
                rec.checks_passed.append("output_integrity_export_skipped")

        rec.ok = len(rec.errors) == 0
        if write_per_dataset_audit:
            _write_dataset_audit(batch_root, rec, validated_at=validated_at)

    # Duplicates across batch
    fp_counts = Counter(all_fps)
    dupes = [fp for fp, c in fp_counts.items() if c > 1]
    if dupes:
        errors.append(f"duplicate case_fingerprint(s) in batch: {len(dupes)} unique repeated hash(es)")

    dist_err, dist_warn = _distribution_checks(len(cases), cases, strict=strict_distribution)
    errors.extend(dist_err)
    warnings.extend(dist_warn)

    all_ok = not errors and all(r.ok for r in per_dataset.values())
    report = BatchValidationReport(
        batch_root=batch_root,
        ok=all_ok,
        errors=errors,
        warnings=warnings,
        dataset_count=len(per_dataset),
        per_dataset=per_dataset,
        duplicate_fingerprints=dupes,
    )

    if write_batch_report:
        manifests = batch_root / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        out = {
            "format": "taxweave-atlas-delivery-validation-v1",
            "validated_at_utc": validated_at,
            "batch_root": str(batch_root),
            "ok": report.ok,
            "expect_pdfs": expect_pdfs,
            "strict_distribution": strict_distribution,
            "summary": report.summary_line(),
            "errors": report.errors,
            "warnings": report.warnings,
            "duplicate_fingerprints": report.duplicate_fingerprints,
            "datasets": {
                slug: {
                    "ok": r.ok,
                    "case_fingerprint": r.case_fingerprint,
                    "errors": r.errors,
                    "warnings": r.warnings,
                    "checks_passed": r.checks_passed,
                    "blueprint_compliance": r.blueprint_compliance,
                }
                for slug, r in sorted(per_dataset.items())
            },
        }
        (manifests / "delivery_validation_report.json").write_text(
            json.dumps(out, indent=2) + "\n",
            encoding="utf-8",
        )

    log.debug("%s", report.summary_line())
    return report
