#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.services.ticket_debug import build_stress_ticket_dto  # noqa: E402
from backend.services.ticket_pdf import render_ticket_html_pdf, render_ticket_pdf  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Render ticket template with stress-test data.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write ticket_stress.html and ticket_stress.pdf",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write artifacts into /tmp with a timestamped prefix.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    if args.debug:
        output_dir = Path("/tmp").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dto = build_stress_ticket_dto()
    deep_link = dto.get("deep_link")

    html = render_ticket_html_pdf(dto, deep_link)
    suffix = ""
    if args.debug:
        suffix = "_" + datetime.now().strftime("%Y%m%d%H%M%S")
    html_path = output_dir / f"ticket_stress{suffix}.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_bytes = render_ticket_pdf(dto, deep_link)
    pdf_path = output_dir / f"ticket_stress{suffix}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    print(f"Wrote {html_path}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
