from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            name="TwPdfTitle",
            parent=base["Heading1"],
            fontSize=15,
            spaceAfter=12,
            textColor=colors.HexColor("#1a2e1a"),
        ),
        "body": ParagraphStyle(
            name="TwPdfBody",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
        ),
        "footer": ParagraphStyle(
            name="TwPdfFooter",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#555555"),
        ),
    }


def _format_cell_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_mapped_fields_pdf(*, title: str, subtitle: str, fields: dict[str, Any]) -> bytes:
    """
    Build a flat, presentation-ready PDF (no AcroForm fields — content is fixed at render time).
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.72 * inch,
        title=title[:100],
    )
    st = _styles()
    story: list[Any] = []
    story.append(Paragraph(_escape_xml(title), st["title"]))
    story.append(Paragraph(f"<i>{_escape_xml(subtitle)}</i>", st["footer"]))
    story.append(Spacer(1, 0.18 * inch))

    data = [["Field", "Value"]]
    for label, value in fields.items():
        pretty_label = label.replace("_", " ").title()
        data.append([pretty_label, _format_cell_value(value)])

    table = Table(data, colWidths=[2.35 * inch, 4.25 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eee8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a2e1a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cfd8cf")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.28 * inch))
    story.append(
        Paragraph(
            "<i>Synthetic data for testing and training only. Not for filing. "
            "Fields are baked into the page (no fillable widgets).</i>",
            st["footer"],
        )
    )
    doc.build(story)
    return buf.getvalue()
