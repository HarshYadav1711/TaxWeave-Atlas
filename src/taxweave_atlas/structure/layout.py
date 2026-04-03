"""
Write staging (full internal tree) and PDF-only export trees per ``dataset_structure_blueprint.yaml``.

Every artifact is derived from a single reconciled ``SyntheticTaxCase`` (see ``schema.case``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from taxweave_atlas.exceptions import ConfigurationError, RendererError
from taxweave_atlas.generation.uniqueness import case_fingerprint
from taxweave_atlas.reconciliation.checks import validate_reconciled_case
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.structure.blueprint import (
    build_layout_context,
    expected_root_outer_names,
    iter_export_layout_file_specs,
    iter_layout_file_specs,
    load_structure_blueprint,
)
from taxweave_atlas.structure.case_copy import (
    attachments_index_paragraphs,
    build_mef_subset_prompt_xml,
    client_summary_paragraphs,
    completed_forms_summary_paragraphs,
    executive_brief_docx_paragraphs,
    prompt_companion_docx_paragraphs,
)
from taxweave_atlas.structure.minimal_office import (
    write_minimal_docx,
    write_minimal_xlsx,
    write_paragraphs_docx,
)

EXPORT_MANIFEST_FILENAME = "manifest.json"
EXPORT_MANIFEST_FORMAT = "taxweave-atlas-dataset-export-v1"
STAGING_MANIFEST_FILENAME = "00_dataset_files_manifest.json"


def _generator_bytes(generator_id: str, case: SyntheticTaxCase) -> bytes:
    """Lazy-import PDF pipeline to avoid import cycles."""
    from taxweave_atlas.pdf import pipeline as pdf_pipeline
    from taxweave_atlas.pdf.reportlab_render import (
        render_minimal_invoice_pdf,
        render_paragraphs_pdf,
    )

    if generator_id == "minimal_docx":
        raise ConfigurationError("minimal_docx is not a byte generator")
    if generator_id == "minimal_xlsx":
        raise ConfigurationError("minimal_xlsx is not a byte generator")
    if generator_id == "prompt_xml":
        raise ConfigurationError("prompt_xml is not a byte generator")

    if generator_id == "pdf_w2":
        return pdf_pipeline.materialize_mapped_pdf_bytes(
            case, renderer_name="supporting_w2", mapping_document="supporting_w2"
        )
    if generator_id == "pdf_1099_int":
        return pdf_pipeline.materialize_mapped_pdf_bytes(
            case, renderer_name="supporting_1099_int", mapping_document="supporting_1099_int"
        )
    if generator_id == "pdf_1099_div":
        return pdf_pipeline.materialize_mapped_pdf_bytes(
            case, renderer_name="supporting_1099_div", mapping_document="supporting_1099_div"
        )
    if generator_id == "pdf_executive":
        return pdf_pipeline.materialize_mapped_pdf_bytes(
            case, renderer_name="executive_summary", mapping_document="executive_summary"
        )
    if generator_id == "pdf_combined_return":
        return pdf_pipeline.materialize_combined_return_pdf_bytes(case)
    if generator_id == "pdf_invoice":
        return render_minimal_invoice_pdf(
            tax_year=case.tax_year, taxpayer_label=case.profile.taxpayer_label
        )
    if generator_id == "pdf_client_summary":
        return render_paragraphs_pdf(
            title=f"Client summary — TY {case.tax_year}",
            subtitle="Synthetic intake summary (PDF deliverable; DOCX variant in _staging only)",
            paragraphs=client_summary_paragraphs(case),
        )
    if generator_id == "pdf_attachments_summary":
        return render_paragraphs_pdf(
            title=f"Tax document attachments summary — TY {case.tax_year}",
            subtitle="Category index aligned to supporting PDFs",
            paragraphs=attachments_index_paragraphs(case),
        )
    if generator_id == "pdf_completed_forms_summary":
        return render_paragraphs_pdf(
            title=f"Completed forms summary — TY {case.tax_year}",
            subtitle="Return package overview",
            paragraphs=completed_forms_summary_paragraphs(case),
        )
    if generator_id == "pdf_bank_statement_placeholder":
        return render_paragraphs_pdf(
            title=f"Bank statement (synthetic placeholder) — TY {case.tax_year}",
            subtitle="Internal XLSX workbook exists under _staging; this PDF is the handoff artifact",
            paragraphs=[
                "Placeholder bank statement summary for synthetic training data.",
                "No real account data. Figures reconcile to the same SyntheticTaxCase as other artifacts.",
            ],
        )
    if generator_id == "pdf_schedule_c_placeholder":
        return render_paragraphs_pdf(
            title=f"Schedule C workbook (synthetic placeholder) — TY {case.tax_year}",
            subtitle="Internal XLSX exists under _staging; PDF provided for PDF-only deliverable rules",
            paragraphs=[
                "Placeholder Schedule C–style summary (not full IRS Schedule C).",
                "SyntheticTaxCase does not emit full Schedule C XML; see TaxWeaveAtlasCoverage in prompt XML.",
            ],
        )
    raise ConfigurationError(f"Unknown structure generator {generator_id!r}")


def _write_contract_docx(rel_posix: str, out_path: Path, case: SyntheticTaxCase) -> None:
    if rel_posix.endswith("Client Summary.docx"):
        write_paragraphs_docx(out_path, client_summary_paragraphs(case))
    elif rel_posix.endswith("Tax Document Attachments Summary.docx"):
        write_paragraphs_docx(out_path, attachments_index_paragraphs(case))
    elif rel_posix.endswith("Completed forms - Summary.docx"):
        write_paragraphs_docx(out_path, completed_forms_summary_paragraphs(case))
    elif rel_posix.endswith("4. Summary_.docx"):
        write_paragraphs_docx(out_path, executive_brief_docx_paragraphs(case))
    elif rel_posix.endswith("Tax Return Data - Prompt.docx"):
        write_paragraphs_docx(out_path, prompt_companion_docx_paragraphs(case))
    else:
        write_minimal_docx(out_path)


def _remove_staging_generated_paths(
    staging_dir: Path,
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
) -> None:
    for outer in expected_root_outer_names(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    ):
        p = staging_dir / outer
        if p.is_dir():
            shutil.rmtree(p)
    mp = staging_dir / STAGING_MANIFEST_FILENAME
    if mp.is_file():
        mp.unlink()


def _clear_export_directory(export_dir: Path) -> None:
    if not export_dir.is_dir():
        return
    for child in list(export_dir.iterdir()):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def _materialize_specs(
    dataset_dir: Path,
    case: SyntheticTaxCase,
    specs: list[tuple[str, str]],
) -> dict[str, str]:
    files_sha256: dict[str, str] = {}
    for rel_posix, gen_id in specs:
        out_path = dataset_dir.joinpath(*rel_posix.split("/"))

        if gen_id == "minimal_docx":
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                _write_contract_docx(rel_posix, out_path, case)
            except OSError as e:
                raise RendererError(f"write failed {rel_posix}: {e}") from e
            payload = out_path.read_bytes()
        elif gen_id == "minimal_xlsx":
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                write_minimal_xlsx(out_path)
            except OSError as e:
                raise RendererError(f"write failed {rel_posix}: {e}") from e
            payload = out_path.read_bytes()
        elif gen_id == "prompt_xml":
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(build_mef_subset_prompt_xml(case))
            except OSError as e:
                raise RendererError(f"write failed {rel_posix}: {e}") from e
            payload = out_path.read_bytes()
        else:
            try:
                payload = _generator_bytes(gen_id, case)
            except Exception as e:
                raise RendererError(f"render failed {rel_posix} ({gen_id}): {e}") from e
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(payload)

        files_sha256[rel_posix] = hashlib.sha256(payload).hexdigest()
    return files_sha256


def write_staging_dataset_structure_bundle(
    case: SyntheticTaxCase,
    staging_dir: Path,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    reconcile_first: bool = False,
    clean_generated: bool = True,
) -> Path:
    """
    Full internal tree under ``staging_dir`` (DOCX, XLSX, XML, PDF, prompt) plus
    ``00_dataset_files_manifest.json`` covering every contract path.
    """
    if reconcile_first:
        from taxweave_atlas.reconciliation.pipeline import reconcile_case

        case = reconcile_case(case)
    else:
        validate_reconciled_case(case)

    bp = load_structure_blueprint()
    blueprint_version = int(bp["version"])
    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    export_token = ctx["export_token"]
    specs = iter_layout_file_specs(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )

    if clean_generated:
        _remove_staging_generated_paths(
            staging_dir, case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
        )

    # ``files_sha256`` insertion order must match ``specs`` (blueprint contract; validated on delivery).
    files_sha256 = _materialize_specs(staging_dir, case, specs)

    case_payload = case.model_dump_json(exclude_computed_fields=True)
    case_hash = hashlib.sha256(case_payload.encode("utf-8")).hexdigest()
    fp = case_fingerprint(case)

    sidecar = {
        "format": "taxweave-atlas-dataset-files-v2",
        "structure_blueprint_version": blueprint_version,
        "export_token": export_token,
        "tax_year": case.tax_year,
        "case_fingerprint": fp,
        "case_json_sha256": case_hash,
        "files_sha256": files_sha256,
        "canonical_case_model": "SyntheticTaxCase",
    }
    manifest_path = staging_dir / STAGING_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def write_export_pdf_bundle(
    case: SyntheticTaxCase,
    export_dir: Path,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    reconcile_first: bool = False,
) -> Path:
    """
    PDF-only deliverable tree + ``manifest.json`` (checksums for export paths only).
    """
    if reconcile_first:
        from taxweave_atlas.reconciliation.pipeline import reconcile_case

        case = reconcile_case(case)
    else:
        validate_reconciled_case(case)

    bp = load_structure_blueprint()
    blueprint_version = int(bp["version"])
    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    export_token = ctx["export_token"]
    specs = iter_export_layout_file_specs(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )

    export_dir.mkdir(parents=True, exist_ok=True)
    _clear_export_directory(export_dir)

    for rel, _gen in specs:
        if not str(rel).lower().endswith(".pdf"):
            raise RendererError(f"export contract must be PDF-only, got {rel!r}")

    # Key order matches ``iter_export_layout_file_specs`` (enforced at validate-batch).
    files_sha256 = _materialize_specs(export_dir, case, specs)

    case_payload = case.model_dump_json(exclude_computed_fields=True)
    case_hash = hashlib.sha256(case_payload.encode("utf-8")).hexdigest()
    fp = case_fingerprint(case)

    sidecar = {
        "format": EXPORT_MANIFEST_FORMAT,
        "structure_blueprint_version": blueprint_version,
        "export_token": export_token,
        "tax_year": case.tax_year,
        "case_fingerprint": fp,
        "case_json_sha256": case_hash,
        "files_sha256": files_sha256,
        "canonical_case_model": "SyntheticTaxCase",
    }
    manifest_path = export_dir / EXPORT_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return manifest_path
