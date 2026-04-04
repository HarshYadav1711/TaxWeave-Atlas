"""IRS fillable-PDF templates: cache, AcroForm fill, Form 1040 + schedule helpers."""

from __future__ import annotations

from taxweave_atlas.pdf.irs.f1040 import render_filled_f1040_pdf_bytes
from taxweave_atlas.pdf.irs.schedules import render_filled_schedule_pdf_bytes

__all__ = ["render_filled_f1040_pdf_bytes", "render_filled_schedule_pdf_bytes"]
