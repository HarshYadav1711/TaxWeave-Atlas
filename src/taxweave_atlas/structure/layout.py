"""
Write the full dataset folder tree per ``dataset_structure_blueprint.yaml`` and checksum manifest.

Every artifact is derived from a single reconciled ``SyntheticTaxCase`` (see ``schema.case``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from taxweave_atlas.exceptions import ConfigurationError, RendererError
from taxweave_atlas.generation.uniqueness import case_fingerprint
from taxweave_atlas.reconciliation.checks import validate_reconciled_case
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.structure.blueprint import (
    build_layout_context,
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


def _generator_bytes(generator_id: str, case: SyntheticTaxCase) -> bytes:
    """Lazy-import PDF pipeline to avoid import cycles."""
    from taxweave_atlas.pdf.reportlab_render import render_minimal_invoice_pdf
    from taxweave_atlas.pdf import pipeline as pdf_pipeline

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


def write_dataset_structure_bundle(
    case: SyntheticTaxCase,
    dataset_dir: Path,
    *,
    dataset_index: int,
    uniqueness_salt: int,
    reconcile_first: bool = False,
) -> Path:
    """
    Materialize the full reference-aligned tree under ``dataset_dir`` and write
    ``00_dataset_files_manifest.json`` with ``files_sha256`` for every file (posix keys).
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

    files_sha256: dict[str, str] = {}

    for rel_posix, gen_id in specs:
        out_path = dataset_dir.joinpath(*rel_posix.split("/"))

        if gen_id == "minimal_docx":
            try:
                _write_contract_docx(rel_posix, out_path, case)
            except OSError as e:
                raise RendererError(f"write failed {rel_posix}: {e}") from e
            payload = out_path.read_bytes()
        elif gen_id == "minimal_xlsx":
            try:
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
    manifest_path = dataset_dir / "00_dataset_files_manifest.json"
    manifest_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return manifest_path
