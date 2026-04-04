"""
Merged complete return PDF: Form 1040 + supporting schedules in a fixed page order.

Uses ``pypdf`` to concatenate single-page (or multi-page) ReportLab PDFs. All slices are
derived from the reconciled ``SyntheticTaxCase``.
"""

from __future__ import annotations

from io import BytesIO
from typing import Final

from pypdf import PdfReader, PdfWriter

from taxweave_atlas.exceptions import ConfigurationError, RendererError
from taxweave_atlas.pdf.irs import render_filled_f1040_pdf_bytes, render_filled_schedule_pdf_bytes
from taxweave_atlas.pdf.mappings import load_pdf_mappings, materialize_mapping_document
from taxweave_atlas.pdf.reportlab_render import render_mapped_fields_pdf
from taxweave_atlas.schema.case import SyntheticTaxCase

# Page order in the merged handoff PDF (Form 1040 first; schedules only if present on the case).
MERGE_ELEMENTS_ORDER: Final[tuple[str | None, ...]] = (
    None,  # Form 1040 (federal line summary)
    "IRS1040Schedule1",
    "IRS1040Schedule2",
    "IRS1040ScheduleB",
    "IRS1040ScheduleC",
    "IRS1040ScheduleSE",
    "IRS1040Schedule8812",
    "IRS8995",
    "IRS4562",
    "IRS8867",
)


def form_1040_single_pdf_bytes(case: SyntheticTaxCase) -> bytes:
    """Official IRS Form 1040 fillable template when available; else mapping-backed summary PDF."""
    try:
        return render_filled_f1040_pdf_bytes(case)
    except RendererError:
        mapping_docs = load_pdf_mappings()
        case_dict = case.model_dump(mode="json")
        fields = materialize_mapping_document("federal_summary", case_dict, documents=mapping_docs)
        return render_mapped_fields_pdf(
            title=f"Form 1040 (line summary) — TY {case.tax_year}",
            subtitle="Synthetic reconciled federal lines (IRS template unavailable; summary layout)",
            fields=fields,
        )


def structural_form_single_pdf_bytes(case: SyntheticTaxCase, element_name: str) -> bytes:
    """Official IRS schedule PDF when mapped and downloadable; else summary PDF."""
    doc = next((d for d in case.structural_mef.documents if d.element_name == element_name), None)
    if doc is None:
        raise ConfigurationError(f"No structural_mef document {element_name!r} on case")
    try:
        return render_filled_schedule_pdf_bytes(case, element_name)
    except RendererError:
        pass
    fields = {str(k): v for k, v in doc.fields.items()}
    return render_mapped_fields_pdf(
        title=f"{element_name} — TY {case.tax_year}",
        subtitle="Synthetic structural totals (IRS template unavailable; summary layout)",
        fields=fields,
    )


def collect_ordered_return_pdf_parts(case: SyntheticTaxCase) -> tuple[list[bytes], list[str]]:
    """
    Build ordered PDF byte chunks for merge: always Form 1040, then each present schedule
    in ``MERGE_ELEMENTS_ORDER``.
    """
    parts: list[bytes] = [form_1040_single_pdf_bytes(case)]
    labels: list[str] = ["Form_1040"]
    present = {d.element_name for d in case.structural_mef.documents}
    for el in MERGE_ELEMENTS_ORDER[1:]:
        if el is None:
            continue
        if el in present:
            parts.append(structural_form_single_pdf_bytes(case, el))
            labels.append(el)
    return parts, labels


def validate_merge_order(case: SyntheticTaxCase, labels: list[str]) -> None:
    present = {d.element_name for d in case.structural_mef.documents}
    expected = ["Form_1040"] + [e for e in MERGE_ELEMENTS_ORDER[1:] if e and e in present]
    if labels != expected:
        raise RendererError(f"complete return merge order mismatch: got {labels} expected {expected}")


def merge_pdf_parts(parts: list[bytes]) -> bytes:
    if not parts:
        raise RendererError("complete return merge: no PDF parts to merge")
    writer = PdfWriter()
    expected_pages = 0
    try:
        for raw in parts:
            reader = PdfReader(BytesIO(raw))
            n = len(reader.pages)
            expected_pages += n
            for page in reader.pages:
                writer.add_page(page)
        out = BytesIO()
        writer.write(out)
        merged = out.getvalue()
    except Exception as e:
        raise RendererError(f"complete return PDF merge failed: {e}") from e

    # Verify merged page count matches source parts (order sanity check).
    check = PdfReader(BytesIO(merged))
    if len(check.pages) != expected_pages:
        raise RendererError(
            f"complete return merge: page count mismatch (merged={len(check.pages)} "
            f"expected={expected_pages} from {len(parts)} part(s))"
        )
    return merged


def build_merged_complete_return_pdf_bytes(case: SyntheticTaxCase) -> bytes:
    """Single PDF: Form 1040 section + present schedules in ``MERGE_ELEMENTS_ORDER``."""
    parts, labels = collect_ordered_return_pdf_parts(case)
    validate_merge_order(case, labels)
    return merge_pdf_parts(parts)


def extend_complete_form_individual_specs(case: SyntheticTaxCase, base: str) -> list[tuple[str, str]]:
    """
    Extra blueprint paths under ``3. Complete form/…``: Form-1040.pdf plus one PDF per
    emitted structural schedule (names match MeF element tags).
    """
    rows: list[tuple[str, str]] = [(f"{base}/Form-1040.pdf", "pdf_form_1040_only")]
    present = {d.element_name for d in case.structural_mef.documents}
    for el in MERGE_ELEMENTS_ORDER[1:]:
        if el and el in present:
            rows.append((f"{base}/{el}.pdf", f"pdf_structural_form:{el}"))
    return rows
