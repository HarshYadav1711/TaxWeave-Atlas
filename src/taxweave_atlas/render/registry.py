from __future__ import annotations

from typing import Any, Callable

from taxweave_atlas.exceptions import RendererError
from taxweave_atlas.mapping import materialize_document
from taxweave_atlas.render.pdf_base import build_simple_pdf


def _rows_from_mapping(fields: dict[str, Any]) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for k, v in fields.items():
        if v is None:
            disp = "N/A"
        elif isinstance(v, bool):
            disp = "Yes" if v else "No"
        else:
            disp = v
        rows.append((k.replace("_", " ").title(), disp))
    return rows


def render_questionnaire(fields: dict[str, Any]) -> bytes:
    title = f"Synthetic Tax Intake Questionnaire — TY {fields['tax_year']}"
    return build_simple_pdf(title, _rows_from_mapping(fields))


def render_supporting_w2(fields: dict[str, Any]) -> bytes:
    title = f"Synthetic Form W-2 Summary — TY {fields['tax_year']}"
    return build_simple_pdf(title, _rows_from_mapping(fields))


def render_supporting_1099_int(fields: dict[str, Any]) -> bytes:
    title = f"Synthetic Form 1099-INT Summary — TY {fields['tax_year']}"
    return build_simple_pdf(title, _rows_from_mapping(fields))


def render_federal_summary(fields: dict[str, Any]) -> bytes:
    title = f"Synthetic Federal Return Summary — TY {fields['tax_year']}"
    return build_simple_pdf(title, _rows_from_mapping(fields))


def render_state_summary(fields: dict[str, Any]) -> bytes:
    title = f"Synthetic State Return Summary — {fields['state_code']} — TY {fields['tax_year']}"
    return build_simple_pdf(title, _rows_from_mapping(fields))


def render_executive_summary(fields: dict[str, Any]) -> bytes:
    title = f"Synthetic Executive Summary — TY {fields['tax_year']}"
    return build_simple_pdf(title, _rows_from_mapping(fields))


RENDERERS: dict[str, Callable[[dict[str, Any]], bytes]] = {
    "questionnaire": render_questionnaire,
    "supporting_w2": render_supporting_w2,
    "supporting_1099_int": render_supporting_1099_int,
    "federal_summary": render_federal_summary,
    "state_summary": render_state_summary,
    "executive_summary": render_executive_summary,
}


def render_deliverable(renderer_name: str, mapping_document: str, case_dict: dict[str, Any]) -> bytes:
    if renderer_name not in RENDERERS:
        raise RendererError(f"Unknown renderer {renderer_name!r} — update registry.py")
    fields = materialize_document(mapping_document, case_dict)
    return RENDERERS[renderer_name](fields)
