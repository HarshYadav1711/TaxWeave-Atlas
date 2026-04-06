from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from taxweave_atlas.exceptions import RendererError
from taxweave_atlas.pdf.acroform_viewer_fix import strip_text_field_appearance_streams


def match_field_key(reader: PdfReader, tail: str) -> str | None:
    """
    Return the unique AcroForm key whose full name ends with ``tail``
    (e.g. ``\".Page1[0].f1_38[0]\"`` or ``\"Address_ReadOrder[0].f1_20[0]\"``).
    """
    fields = reader.get_fields() or {}
    hits = [k for k in fields if k.endswith(tail)]
    if len(hits) == 1:
        return hits[0]
    return None


def fill_acroform_pdf(
    template_bytes: bytes,
    values: Mapping[str, str],
    *,
    need_appearances: bool = True,
) -> bytes:
    """Clone template, apply text/button field values, write PDF bytes."""
    if not values:
        return template_bytes
    reader = PdfReader(BytesIO(template_bytes))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    if need_appearances:
        root = writer.root_object
        acro_ref = root.get(NameObject("/AcroForm"))
        if acro_ref:
            acro = acro_ref.get_object() if hasattr(acro_ref, "get_object") else acro_ref
            if isinstance(acro, dict):
                acro[NameObject("/NeedAppearances")] = BooleanObject(True)

    # pypdf applies only widgets on each page; passing the full map on every page is supported.
    for page in writer.pages:
        writer.update_page_form_field_values(page, dict(values), auto_regenerate=True)

    out = BytesIO()
    try:
        writer.write(out)
    except Exception as e:
        raise RendererError(f"AcroForm write failed: {e}") from e
    # Drop pypdf-generated /AP for text fields so viewers (e.g. Chrome) place /V text in the box.
    return strip_text_field_appearance_streams(out.getvalue())
