from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from typing import Any

import yaml
from pypdf import PdfReader

from taxweave_atlas.exceptions import ConfigurationError, RendererError
from taxweave_atlas.paths import irs_acroform_maps_path
from taxweave_atlas.pdf.irs.acroform import fill_acroform_pdf, match_field_key
from taxweave_atlas.pdf.irs.cache import get_irs_prior_pdf_bytes
from taxweave_atlas.schema.case import SyntheticTaxCase


def _fmt_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _fmt_ssn(raw: str) -> str:
    d = "".join(c for c in raw if c.isdigit())
    if len(d) == 9:
        return f"{d[:3]}-{d[3:5]}-{d[5:]}"
    return raw.strip()[:11]


@lru_cache(maxsize=1)
def _schedule_maps() -> dict[str, Any]:
    path = irs_acroform_maps_path()
    if not path.is_file():
        raise ConfigurationError(f"Missing IRS schedule map: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "maps" not in data:
        raise ConfigurationError("irs_acroform_schedule_maps.yaml must contain maps:")
    return data["maps"]


def render_filled_schedule_pdf_bytes(case: SyntheticTaxCase, element_name: str) -> bytes:
    """Fill official IRS schedule PDF for a structural_mef document (when mapped)."""
    maps = _schedule_maps()
    spec = maps.get(element_name)
    if not isinstance(spec, dict):
        raise RendererError(f"No IRS AcroForm map for schedule {element_name!r}")

    doc = next((d for d in case.structural_mef.documents if d.element_name == element_name), None)
    if doc is None:
        raise ConfigurationError(f"No structural_mef document {element_name!r} on case")

    slug = str(spec["slug"])
    raw = get_irs_prior_pdf_bytes(slug=slug, year=case.tax_year)
    reader = PdfReader(BytesIO(raw))
    updates: dict[str, str] = {}

    hn = spec.get("header_name")
    if isinstance(hn, str):
        k = match_field_key(reader, hn)
        if k:
            updates[k] = case.profile.primary_full_name.strip()
    hs = spec.get("header_ssn")
    if isinstance(hs, str):
        k = match_field_key(reader, hs)
        if k:
            updates[k] = _fmt_ssn(case.profile.synthetic_ssn_primary)

    fields_spec = spec.get("fields") or {}
    if not isinstance(fields_spec, dict):
        raise ConfigurationError(f"Invalid fields for {element_name!r}")

    for struct_key, tail in fields_spec.items():
        if struct_key not in doc.fields:
            continue
        if not isinstance(tail, str):
            continue
        fk = match_field_key(reader, tail)
        if fk:
            updates[fk] = _fmt_cell(doc.fields[struct_key])

    return fill_acroform_pdf(raw, updates)
