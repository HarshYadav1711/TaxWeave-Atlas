"""
PDF / dataset file bundle: staging tree (internal), PDF-only export, case load helpers.
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
    """
    Render one mapping-backed PDF (used by the dataset structure layout).

    Callers must pass a **fully reconciled** ``SyntheticTaxCase`` (same object shape as after
    ``reconcile_case``): field values are read directly from the case tree with no independent
    tax math here. Typical call path is ``write_*_dataset_structure_bundle``, which runs
    ``validate_reconciled_case`` before any PDF bytes are produced.
    """
    mapping_docs = load_pdf_mappings()
    if mapping_document not in mapping_docs:
        raise ConfigurationError(f"Unknown mapping_document {mapping_document!r}")
    case_dict = case.model_dump(mode="json")
    title, subtitle = _renderer_meta(renderer_name)
    fields = materialize_mapping_document(mapping_document, case_dict, documents=mapping_docs)
    full_title = f"{title} — TY {case.tax_year}"
    return render_mapped_fields_pdf(title=full_title, subtitle=subtitle, fields=fields)


def materialize_combined_return_pdf_bytes(case: SyntheticTaxCase) -> bytes:
    """Federal + state summaries in one PDF (complete-form slot). Uses reconciled case fields only."""
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


def render_dataset_deliverable_trees(
    case: SyntheticTaxCase,
    staging_dir: Path,
    export_dir: Path,
    *,
    reconcile_first: bool = False,
    dataset_index: int | None = None,
    uniqueness_salt: int | None = None,
) -> tuple[Path, Path]:
    """
    Write full internal tree under ``staging_dir`` and PDF-only handoff under ``export_dir``.
    """
    from taxweave_atlas.structure.blueprint import parse_dataset_slug_index
    from taxweave_atlas.structure.layout import (
        write_export_pdf_bundle,
        write_staging_dataset_structure_bundle,
    )

    idx = (
        dataset_index
        if dataset_index is not None
        else parse_dataset_slug_index(staging_dir.name)
    )
    salt = 0 if uniqueness_salt is None else int(uniqueness_salt)
    if reconcile_first:
        from taxweave_atlas.reconciliation.pipeline import reconcile_case

        case = reconcile_case(case)
    else:
        from taxweave_atlas.reconciliation.checks import validate_reconciled_case

        validate_reconciled_case(case)
    try:
        m_staging = write_staging_dataset_structure_bundle(
            case,
            staging_dir,
            dataset_index=idx,
            uniqueness_salt=salt,
            reconcile_first=False,
            clean_generated=True,
        )
        m_export = write_export_pdf_bundle(
            case,
            export_dir,
            dataset_index=idx,
            uniqueness_salt=salt,
            reconcile_first=False,
        )
        return m_staging, m_export
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
    """Regenerate staging + export bundles from every ``_staging/datasets/dataset_*/case.json``."""
    from taxweave_atlas.paths import staging_datasets_root
    from taxweave_atlas.structure.blueprint import parse_dataset_slug_index
    from taxweave_atlas.structure.validate import uniqueness_salt_for_slug

    staging_root = staging_datasets_root(batch_root)
    if not staging_root.is_dir():
        raise ConfigurationError(
            f"No _staging/datasets/ under {batch_root} (expected internal build layout)"
        )

    n = 0
    export_root = batch_root / "datasets"
    export_root.mkdir(parents=True, exist_ok=True)
    for case_path in sorted(staging_root.glob("dataset_*/case.json")):
        raw = case_path.read_text(encoding="utf-8")
        case = _parse_case_json_text(raw)
        staging_dir = case_path.parent
        slug = staging_dir.name
        idx = parse_dataset_slug_index(slug)
        salt = uniqueness_salt_for_slug(batch_root, slug)
        export_dir = export_root / slug
        render_dataset_deliverable_trees(
            case,
            staging_dir,
            export_dir,
            reconcile_first=reconcile_first,
            dataset_index=idx,
            uniqueness_salt=salt,
        )
        n += 1
    return n


def load_case_from_path(path: Path) -> SyntheticTaxCase:
    return _parse_case_json_text(path.read_text(encoding="utf-8"))


def resolve_staging_export_dirs(case_json_path: Path) -> tuple[Path, Path]:
    """
    Given ``.../<batch>/_staging/datasets/dataset_XXXXX/case.json``, return (staging_dir, export_dir).
    """
    staging_dir = case_json_path.parent
    try:
        if staging_dir.parts[-3] != "_staging" or staging_dir.parts[-2] != "datasets":
            raise IndexError
    except IndexError as e:
        raise ConfigurationError(
            "case.json must live under <batch_root>/_staging/datasets/dataset_XXXXX/case.json"
        ) from e
    batch_root = staging_dir.parents[2]
    export_dir = batch_root / "datasets" / staging_dir.name
    return staging_dir, export_dir
