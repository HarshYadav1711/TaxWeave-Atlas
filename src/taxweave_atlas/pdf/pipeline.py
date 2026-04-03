from __future__ import annotations

import hashlib
import json
from pathlib import Path

from taxweave_atlas.exceptions import ConfigurationError, RendererError
from taxweave_atlas.generation.uniqueness import case_fingerprint
from taxweave_atlas.pdf.manifest import filter_deliverables, load_template_manifest
from taxweave_atlas.pdf.mappings import load_pdf_mappings, materialize_mapping_document
from taxweave_atlas.pdf.reportlab_render import render_mapped_fields_pdf
from taxweave_atlas.reconciliation.checks import validate_reconciled_case
from taxweave_atlas.schema.case import SyntheticTaxCase


def _renderer_meta(renderer_name: str) -> tuple[str, str]:
    meta: dict[str, tuple[str, str]] = {
        "intake_questionnaire": (
            "Tax intake questionnaire",
            "Synthetic taxpayer intake — values aligned to reconciled case",
        ),
        "supporting_w2": (
            "Supporting document — Form W-2 (summary)",
            "Box values aligned to reconciled wages and withholding",
        ),
        "supporting_1099_int": (
            "Supporting document — Form 1099-INT (summary)",
            "Interest income aligned to federal return",
        ),
        "supporting_1099_div": (
            "Supporting document — Form 1099-DIV (summary)",
            "Ordinary dividends aligned to federal return",
        ),
        "federal_return": (
            "Federal return — line summary",
            "1040-family line summary after reconciliation (synthetic schedule)",
        ),
        "state_return": (
            "State return — line summary",
            "Resident state stub summary aligned to reconciliation rules",
        ),
        "executive_summary": (
            "Executive summary",
            "Key figures derived from reconciled federal and state totals",
        ),
    }
    if renderer_name not in meta:
        raise ConfigurationError(f"No PDF title metadata for renderer {renderer_name!r}")
    return meta[renderer_name]


def render_dataset_pdf_bundle(
    case: SyntheticTaxCase,
    dataset_dir: Path,
    *,
    reconcile_first: bool = False,
) -> Path:
    """
    Write all PDF deliverables plus 00_dataset_files_manifest.json (checksums).
    If reconcile_first is True, re-run reconciliation before rendering (e.g. older case.json).
    """
    if reconcile_first:
        from taxweave_atlas.reconciliation.pipeline import reconcile_case

        case = reconcile_case(case)
    else:
        validate_reconciled_case(case)

    manifest_root = load_template_manifest()
    deliverables = filter_deliverables(manifest_root["deliverables"], case.model_dump(mode="json"))
    mapping_docs = load_pdf_mappings()
    for d in deliverables:
        mk = d.get("mapping_document")
        if mk not in mapping_docs:
            raise ConfigurationError(
                f"Deliverable {d.get('id')!r} mapping_document {mk!r} missing from mappings.yaml"
            )

    case_dict = case.model_dump(mode="json")
    pdf_hashes: dict[str, str] = {}

    for d in deliverables:
        renderer = d["renderer"]
        fname = d["filename"]
        mdoc = d["mapping_document"]
        title, subtitle = _renderer_meta(renderer)
        fields = materialize_mapping_document(mdoc, case_dict, documents=mapping_docs)
        full_title = f"{title} — TY {case.tax_year}"
        try:
            pdf_bytes = render_mapped_fields_pdf(title=full_title, subtitle=subtitle, fields=fields)
        except Exception as e:
            raise RendererError(f"PDF render failed for {fname}: {e}") from e
        out_path = dataset_dir / fname
        out_path.write_bytes(pdf_bytes)
        pdf_hashes[fname] = hashlib.sha256(pdf_bytes).hexdigest()

    case_payload = case.model_dump_json(exclude_computed_fields=True)
    case_hash = hashlib.sha256(case_payload.encode("utf-8")).hexdigest()
    fp = case_fingerprint(case)

    sidecar = {
        "format": "taxweave-atlas-dataset-files-v1",
        "tax_year": case.tax_year,
        "case_fingerprint": fp,
        "case_json_sha256": case_hash,
        "pdf_files_sha256": pdf_hashes,
    }
    manifest_path = dataset_dir / "00_dataset_files_manifest.json"
    manifest_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _parse_case_json_text(raw: str) -> SyntheticTaxCase:
    """Load case from JSON; drop stale keys from older exports (e.g. serialized computed fields)."""
    payload: dict = json.loads(raw)
    prof = payload.get("profile")
    if isinstance(prof, dict):
        prof.pop("primary_full_name", None)
    return SyntheticTaxCase.model_validate(payload)


def render_pdfs_for_batch_output(batch_root: Path, *, reconcile_first: bool = False) -> int:
    """
    Render PDFs for every datasets/dataset_*/case.json under batch_root.
    Returns count of dataset folders processed.
    """
    datasets = batch_root / "datasets"
    if not datasets.is_dir():
        raise ConfigurationError(f"No datasets/ directory under {batch_root}")

    n = 0
    for case_path in sorted(datasets.glob("dataset_*/case.json")):
        raw = case_path.read_text(encoding="utf-8")
        case = _parse_case_json_text(raw)
        render_dataset_pdf_bundle(case, case_path.parent, reconcile_first=reconcile_first)
        n += 1
    return n


def load_case_from_path(path: Path) -> SyntheticTaxCase:
    return _parse_case_json_text(path.read_text(encoding="utf-8"))
