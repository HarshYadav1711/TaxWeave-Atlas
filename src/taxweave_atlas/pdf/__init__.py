"""PDF production (ReportLab, local, no paid services)."""

from taxweave_atlas.pdf.pipeline import (
    load_case_from_path,
    render_dataset_pdf_bundle,
    render_pdfs_for_batch_output,
)
from taxweave_atlas.pdf.stub import PDFRenderRequest

__all__ = [
    "PDFRenderRequest",
    "load_case_from_path",
    "render_dataset_pdf_bundle",
    "render_pdfs_for_batch_output",
]
