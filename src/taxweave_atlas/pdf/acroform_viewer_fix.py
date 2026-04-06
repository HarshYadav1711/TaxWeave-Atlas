"""
Post-process filled PDFs so viewers paint text fields reliably.

``pypdf``'s ``update_page_form_field_values(..., auto_regenerate=True)`` writes ``/AP``
appearance streams for text fields. Some viewers (notably Chrome's built-in PDF viewer)
still draw that content at the wrong offset relative to the widget ``/Rect``, so names and
SSNs can appear as floating text above the boxes while other fields look fine.

Removing ``/AP`` for **text** fields only (``/FT /Tx``) and setting ``/NeedAppearances``
lets the viewer regenerate placement from ``/DA``, ``/V``, and the widget rectangle.
Button/checkbox fields (``/Btn``) keep their appearances so filing-status ticks keep working.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, IndirectObject, NameObject

from taxweave_atlas.exceptions import RendererError


def strip_text_field_appearance_streams(pdf_bytes: bytes) -> bytes:
    """
    Drop ``/AP`` on all widget annotations with ``/FT /Tx``; set ``/NeedAppearances`` true.

    Idempotent enough for PDFs with no AcroForm (no-op beyond clone/write).
    """
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    try:
        writer.clone_document_from_reader(reader)
    except Exception as e:
        raise RendererError(f"PDF clone for appearance strip failed: {e}") from e

    root = writer.root_object
    if root:
        acro_ref = root.get(NameObject("/AcroForm")) or root.get("/AcroForm")
        if acro_ref is not None:
            acro = acro_ref.get_object() if isinstance(acro_ref, IndirectObject) else acro_ref
            if isinstance(acro, dict):
                acro[NameObject("/NeedAppearances")] = BooleanObject(True)

    for page in writer.pages:
        annots_ref = page.get(NameObject("/Annots")) or page.get("/Annots")
        if annots_ref is None:
            continue
        annots = annots_ref.get_object() if isinstance(annots_ref, IndirectObject) else annots_ref
        if not annots:
            continue
        for ref in annots:
            w = ref.get_object()
            sub = w.get(NameObject("/Subtype")) or w.get("/Subtype")
            if sub not in (NameObject("/Widget"), "/Widget"):
                continue
            ft = w.get(NameObject("/FT")) or w.get("/FT")
            if ft not in (NameObject("/Tx"), "/Tx"):
                continue
            for ap_key in (NameObject("/AP"), "/AP"):
                if ap_key in w:
                    del w[ap_key]
                    break

    out = BytesIO()
    try:
        writer.write(out)
    except Exception as e:
        raise RendererError(f"PDF write after appearance strip failed: {e}") from e
    return out.getvalue()
