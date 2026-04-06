"""
PyMuPDF post-processing for pypdf-filled IRS PDFs.

``refresh_pdf_form_appearances`` updates each widget's appearance from its value so the
official IRS layout is preserved with names and amounts in the boxes (typical completed
return look).

``flatten_pdf_form_fields`` optionally bakes values into static page content (no widgets).
"""

from __future__ import annotations

import logging
from io import BytesIO

from taxweave_atlas.exceptions import RendererError

_log = logging.getLogger(__name__)


def refresh_pdf_form_appearances(pdf_bytes: bytes) -> bytes:
    """Regenerate widget /AP streams from field values; keeps fillable IRS layout."""
    try:
        import fitz
    except ImportError:
        _log.warning(
            "pymupdf (import name: fitz) is not installed — skipping PDF form appearance refresh. "
            "Merged/filled PDFs may show empty or misaligned fields in some viewers. "
            "Fix: pip install pymupdf  or  pip install -e .  from the project root."
        )
        return pdf_bytes

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            for w in page.widgets() or []:
                try:
                    w.update()
                except Exception:
                    continue
        buf = BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        return buf.getvalue()
    except Exception as e:
        raise RendererError(f"PDF form appearance refresh failed: {e}") from e
    finally:
        doc.close()


def _checkbox_is_on(val: object) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    if s.lower() == "off":
        return False
    return s in ("1", "Yes", "On", "yes", "on", "/Yes", "/1", "/On")


def _paint_text(page: object, rect: object, text: str) -> None:
    import fitz

    if not text.strip():
        return
    for fs in range(14, 4, -1):
        rc = page.insert_textbox(
            rect,
            text,
            fontsize=fs,
            fontname="helv",
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )
        if rc >= 0:
            return
    page.insert_textbox(
        rect,
        text,
        fontsize=5,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_LEFT,
    )


def _paint_checkbox_mark(page: object, rect: object) -> None:
    import fitz

    fs = min(max(rect.height * 0.65, 6), 14)
    page.insert_textbox(
        rect,
        "X",
        fontsize=fs,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_CENTER,
    )


def flatten_pdf_form_fields(pdf_bytes: bytes) -> bytes:
    """
    Paint each widget's value into the page, then remove the widget annotations.

    Text fields (``/Tx``) and checkboxes (``/Btn`` checkbox style) are handled; other widget
    types are removed without painting (rare in IRS templates we use).
    """
    try:
        import fitz
    except ImportError as e:
        raise RendererError(
            "Flattening PDF forms requires PyMuPDF (pymupdf). Install taxweave-atlas dependencies."
        ) from e

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            widgets = list(page.widgets() or [])
            for w in widgets:
                ft = w.field_type
                rect = w.rect
                val = w.field_value
                if ft == fitz.PDF_WIDGET_TYPE_TEXT:
                    if val not in (None, ""):
                        _paint_text(page, rect, str(val))
                    page.delete_widget(w)
                elif ft == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    if _checkbox_is_on(val):
                        _paint_checkbox_mark(page, rect)
                    page.delete_widget(w)
                else:
                    page.delete_widget(w)
        buf = BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        return buf.getvalue()
    except Exception as e:
        raise RendererError(f"PDF form flatten failed: {e}") from e
    finally:
        doc.close()
