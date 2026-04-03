from __future__ import annotations

from dataclasses import dataclass

from taxweave_atlas.schema.case import SyntheticTaxCase


@dataclass(frozen=True, slots=True)
class PDFRenderRequest:
    """Hook type: map a case + template id to bytes (see pdf.pipeline for implementation)."""

    template_id: str
    case: SyntheticTaxCase
