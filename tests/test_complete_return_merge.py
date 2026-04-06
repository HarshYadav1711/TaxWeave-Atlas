"""Merged complete-return PDF: ordered sections and page accounting."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from taxweave_atlas.exceptions import RendererError
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.pdf.complete_return import (
    MERGE_ELEMENTS_ORDER,
    build_merged_complete_return_pdf_bytes,
    collect_ordered_return_pdf_parts,
    validate_merge_order,
)
from taxweave_atlas.reconciliation.pipeline import reconcile_case
from taxweave_atlas.schema.ids import DatasetIdentity
from taxweave_atlas.structure.blueprint import build_layout_context, iter_export_layout_file_specs
from taxweave_atlas.structure.layout import _generator_bytes
from taxweave_atlas.validation.specs import load_sample_case


def _page_count(raw: bytes) -> int:
    return len(PdfReader(BytesIO(raw)).pages)


def test_merged_pdf_page_count_matches_ordered_parts() -> None:
    case = reconcile_case(load_sample_case())
    parts, labels = collect_ordered_return_pdf_parts(case)
    validate_merge_order(case, labels)
    merged = build_merged_complete_return_pdf_bytes(case)
    expected = sum(_page_count(p) for p in parts)
    assert _page_count(merged) == expected
    # AcroForm merge would collide identical IRS paths across parts; we prefix each part's root
    # field so Form 1040 values (e.g. name) are not overwritten by a later schedule.
    fields = PdfReader(BytesIO(merged)).get_fields() or {}
    assert any(k.startswith("p0_") for k in fields)
    if len(parts) >= 2:
        assert any(k.startswith("p1_") for k in fields)
    present = {d.element_name for d in case.structural_mef.documents}
    want = ["Form_1040"] + [e for e in MERGE_ELEMENTS_ORDER[1:] if e and e in present]
    assert labels == want


def test_validate_merge_order_rejects_wrong_sequence() -> None:
    case = reconcile_case(load_sample_case())
    present = {d.element_name for d in case.structural_mef.documents}
    expected = ["Form_1040"] + [e for e in MERGE_ELEMENTS_ORDER[1:] if e and e in present]
    if len(expected) < 3:
        pytest.skip("need at least two structural schedules to swap merge order")
    bad = list(expected)
    bad[1], bad[2] = bad[2], bad[1]
    try:
        validate_merge_order(case, bad)
    except RendererError:
        return
    raise AssertionError("expected RendererError for wrong merge label order")


def test_blueprint_includes_merged_and_individual_pdfs() -> None:
    case = reconcile_case(
        build_synthetic_case(
            master_seed=9101,
            identity=DatasetIdentity(index=0),
            salt=0,
            complexity_override="medium",
            state_override="NY",
            tax_year_override=2024,
        )
    )
    ctx = build_layout_context(case, dataset_index=0, uniqueness_salt=1)
    last = ctx["primary_last_safe"]
    first = ctx["primary_first_safe"]
    ty = case.tax_year
    specs = iter_export_layout_file_specs(case, dataset_index=0, uniqueness_salt=1)
    rels = [p for p, _ in specs]
    merged_name = f"{ty}_{last}_{first}_CompleteReturn.pdf"
    assert any(r.endswith(f"/3. Complete form/{merged_name}") for r in rels)
    assert any(r.endswith("/3. Complete form/Form-1040.pdf") for r in rels)


def test_generator_pdf_merged_complete_return() -> None:
    case = reconcile_case(load_sample_case())
    raw = _generator_bytes("pdf_merged_complete_return", case)
    assert _page_count(raw) >= 1
