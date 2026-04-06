"""
Prefix AcroForm root field names so merged PDFs do not collide when using ``PdfWriter.append``.

IRS templates reuse internal paths across forms; prefixing each part's root ``/Fields`` entry
(``p0_``, ``p1_``, …) keeps qualified names unique before append.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import IndirectObject, NameObject, TextStringObject


def _prefix_root_field_partial_name(field_obj: object, prefix: str) -> None:
    if isinstance(field_obj, IndirectObject):
        field_obj = field_obj.get_object()
    if not isinstance(field_obj, dict):
        return
    d = field_obj
    t_key = NameObject("/T") if NameObject("/T") in d else ("/T" if "/T" in d else None)
    if t_key is None:
        return
    old = d[t_key]
    s = old.decode("latin-1") if isinstance(old, bytes) else str(old)
    d[t_key] = TextStringObject(prefix + s)


def prefix_acroform_field_names(raw: bytes, prefix: str) -> bytes:
    """Return a copy of ``raw`` with each root ``/AcroForm``/``/Fields`` entry's ``/T`` prefixed."""
    reader = PdfReader(BytesIO(raw))
    writer = PdfWriter()
    writer.append(reader)
    root = writer.root_object
    if root is None:
        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    acro = root.get("/AcroForm")
    if acro is None:
        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    acro_obj = acro.get_object() if isinstance(acro, IndirectObject) else acro
    if not isinstance(acro_obj, dict):
        out = BytesIO()
        writer.write(out)
        return out.getvalue()
    fields = acro_obj.get(NameObject("/Fields")) or acro_obj.get("/Fields")
    if fields:
        for field_ref in fields:
            _prefix_root_field_partial_name(field_ref, prefix)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
