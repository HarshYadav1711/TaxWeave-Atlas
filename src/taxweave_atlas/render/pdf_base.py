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
    title = ParagraphStyle(
        name="TwTitle",
        parent=base["Heading1"],
        fontSize=16,
        spaceAfter=14,
        textColor=colors.HexColor("#1a2e1a"),
    )
    body = ParagraphStyle(
        name="TwBody",
        parent=base["Normal"],
        fontSize=10,
        leading=13,
    )
    label = ParagraphStyle(
        name="TwLabel",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#444444"),
    )
    return {"title": title, "body": body, "label": label}


def build_simple_pdf(title: str, rows: list[tuple[str, Any]]) -> bytes:
    """rows: (label, value) for a two-column fact sheet."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title,
    )
    st = _styles()
    story: list[Any] = []
    story.append(Paragraph(title.replace("&", "&amp;"), st["title"]))
    story.append(Spacer(1, 0.15 * inch))

    data = [["Field", "Value"]]
    for label, value in rows:
        data.append([label, str(value)])

    t = Table(data, colWidths=[2.4 * inch, 4.2 * inch])
    t.setStyle(
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
    story.append(t)
    story.append(Spacer(1, 0.25 * inch))
    story.append(
        Paragraph(
            "<i>Synthetic data for research and testing only. Not for filing.</i>",
            st["label"],
        )
    )
    doc.build(story)
    return buf.getvalue()
