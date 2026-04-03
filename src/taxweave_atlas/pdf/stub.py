from __future__ import annotations

from dataclasses import dataclass

from taxweave_atlas.exceptions import NotImplementedStageError
from taxweave_atlas.schema.case import SyntheticTaxCase


@dataclass(frozen=True, slots=True)
class PDFRenderRequest:
    """Future hook: map a case + template id to bytes."""

    template_id: str
    case: SyntheticTaxCase


def assert_pdf_pipeline_not_implemented() -> None:
    raise NotImplementedStageError(
        "PDF rendering is not implemented — add template engines under taxweave_atlas.pdf."
    )
