"""
PDF / dataset file bundle: blueprint-aligned tree, checksum manifest, case load helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

from taxweave_atlas.exceptions import ConfigurationError, RendererError
from taxweave_atlas.pdf.mappings import load_pdf_mappings, materialize_mapping_document
from taxweave_atlas.pdf.reportlab_render import (
    render_combined_federal_state_pdf,
    render_mapped_fields_pdf,
)
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
            "Simplified resident-state summary (synthetic rules; not filing advice)",
        ),
        "executive_summary": (
            "Executive summary",
            "Key figures derived from reconciled federal and state totals",
        ),
    }
    if renderer_name not in meta:
        raise ConfigurationError(f"No PDF title metadata for renderer {renderer_name!r}")
    return meta[renderer_name]


def materialize_mapped_pdf_bytes(
    case: SyntheticTaxCase,
    *,
    renderer_name: str,
    mapping_document: str,
) -> bytes:
    """Render one mapping-backed PDF (used by the dataset structure layout)."""
    mapping_docs = load_pdf_mappings()
    if mapping_document not in mapping_docs:
        raise ConfigurationError(f"Unknown mapping_document {mapping_document!r}")
    case_dict = case.model_dump(mode="json")
    title, subtitle = _renderer_meta(renderer_name)
    fields = materialize_mapping_document(mapping_document, case_dict, documents=mapping_docs)
    full_title = f"{title} — TY {case.tax_year}"
    return render_mapped_fields_pdf(title=full_title, subtitle=subtitle, fields=fields)


def materialize_combined_return_pdf_bytes(case: SyntheticTaxCase) -> bytes:
    """Federal + state summaries in one PDF (complete-form slot)."""
    mapping_docs = load_pdf_mappings()
    case_dict = case.model_dump(mode="json")
    federal_fields = materialize_mapping_document("federal_summary", case_dict, documents=mapping_docs)
    state_fields = materialize_mapping_document("state_summary", case_dict, documents=mapping_docs)
    ft, fs = _renderer_meta("federal_return")
    st, ss = _renderer_meta("state_return")
    return render_combined_federal_state_pdf(
        tax_year=case.tax_year,
        federal_title=f"{ft} — TY {case.tax_year}",
        federal_subtitle=fs,
        federal_fields=federal_fields,
        state_title=f"{st} — TY {case.tax_year}",
        state_subtitle=ss,
        state_fields=state_fields,
    )


def render_dataset_pdf_bundle(
    case: SyntheticTaxCase,
    dataset_dir: Path,
    *,
    reconcile_first: bool = False,
    dataset_index: int | None = None,
    uniqueness_salt: int | None = None,
) -> Path:
    """
    Write the full sample-aligned folder tree and ``00_dataset_files_manifest.json`` (v2).

    ``dataset_index`` / ``uniqueness_salt`` default from folder name and 0 when omitted
    (use explicit values from batch generation for correct export tokens).
    """
    from taxweave_atlas.structure.blueprint import parse_dataset_slug_index
    from taxweave_atlas.structure.layout import write_dataset_structure_bundle

    idx = (
        dataset_index
        if dataset_index is not None
        else parse_dataset_slug_index(dataset_dir.name)
    )
    salt = 0 if uniqueness_salt is None else int(uniqueness_salt)
    try:
        return write_dataset_structure_bundle(
            case,
            dataset_dir,
            dataset_index=idx,
            uniqueness_salt=salt,
            reconcile_first=reconcile_first,
        )
    except RendererError:
        raise
    except Exception as e:
        raise RendererError(f"dataset structure render failed: {e}") from e


def _parse_case_json_text(raw: str) -> SyntheticTaxCase:
    """Load case from JSON; drop stale keys from older exports (e.g. serialized computed fields)."""
    payload: dict = json.loads(raw)
    prof = payload.get("profile")
    if isinstance(prof, dict):
        prof.pop("primary_full_name", None)
    return SyntheticTaxCase.model_validate(payload)


def render_pdfs_for_batch_output(batch_root: Path, *, reconcile_first: bool = False) -> int:
    """Regenerate structure bundles for every ``datasets/dataset_*/case.json``."""
    from taxweave_atlas.structure.blueprint import parse_dataset_slug_index
    from taxweave_atlas.structure.validate import uniqueness_salt_for_slug

    datasets = batch_root / "datasets"
    if not datasets.is_dir():
        raise ConfigurationError(f"No datasets/ directory under {batch_root}")

    n = 0
    for case_path in sorted(datasets.glob("dataset_*/case.json")):
        raw = case_path.read_text(encoding="utf-8")
        case = _parse_case_json_text(raw)
        parent = case_path.parent
        slug = parent.name
        idx = parse_dataset_slug_index(slug)
        salt = uniqueness_salt_for_slug(batch_root, slug)
        render_dataset_pdf_bundle(
            case,
            parent,
            reconcile_first=reconcile_first,
            dataset_index=idx,
            uniqueness_salt=salt,
        )
        n += 1
    return n


def load_case_from_path(path: Path) -> SyntheticTaxCase:
    return _parse_case_json_text(path.read_text(encoding="utf-8"))
