"""Development-only endpoints for ticket PDF debugging."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query, Response

from ..services.ticket_debug import build_stress_ticket_dto
from ..services.ticket_pdf import render_ticket_html_pdf, render_ticket_pdf

router = APIRouter(prefix="/dev/tickets", tags=["dev"])


@router.get("/weasyprint")
def get_weasyprint_debug_ticket(debug: bool = Query(False)) -> Response:
    """Render a WeasyPrint PDF with stress-test data."""
    dto = build_stress_ticket_dto()
    deep_link = dto.get("deep_link")

    html = render_ticket_html_pdf(dto, deep_link)
    pdf_bytes = render_ticket_pdf(dto, deep_link)

    if debug:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        html_path = Path("/tmp") / f"ticket_weasy_debug_{timestamp}.html"
        pdf_path = Path("/tmp") / f"ticket_weasy_debug_{timestamp}.pdf"
        html_path.write_text(html, encoding="utf-8")
        pdf_path.write_bytes(pdf_bytes)

    headers = {"Content-Disposition": 'inline; filename="ticket_weasy_debug.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
