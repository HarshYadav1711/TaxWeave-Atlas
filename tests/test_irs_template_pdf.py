"""IRS fillable-template PDFs: Form 1040 and schedules use official layouts when available."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from taxweave_atlas.exceptions import RendererError
from taxweave_atlas.pdf.complete_return import form_1040_single_pdf_bytes, structural_form_single_pdf_bytes
from taxweave_atlas.pdf.irs.f1040 import render_filled_f1040_pdf_bytes
from taxweave_atlas.reconciliation.pipeline import reconcile_case
from taxweave_atlas.validation.specs import load_sample_case


def test_f1040_template_is_two_pages_when_irs_available() -> None:
    try:
        raw = render_filled_f1040_pdf_bytes(reconcile_case(load_sample_case()))
    except RendererError as e:
        pytest.skip(f"IRS template unavailable: {e}")
    assert len(PdfReader(BytesIO(raw)).pages) >= 2


def test_form_1040_single_matches_irs_or_fallback() -> None:
    case = reconcile_case(load_sample_case())
    raw = form_1040_single_pdf_bytes(case)
    assert len(PdfReader(BytesIO(raw)).pages) >= 1


def test_structural_schedule_pdf_bytes_round_trip() -> None:
    case = reconcile_case(load_sample_case())
    present = {d.element_name for d in case.structural_mef.documents}
    if not present:
        pytest.skip("no structural schedules on sample case")
    el = sorted(present)[0]
    raw = structural_form_single_pdf_bytes(case, el)
    assert len(PdfReader(BytesIO(raw)).pages) >= 1
