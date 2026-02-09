#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.services.ticket_pdf import render_ticket_html, render_ticket_pdf  # noqa: E402


def _build_stress_dto() -> dict:
    long_email = "very-long-email-address-with-a-lot-of-parts-and-tags+stress-test-1234567890@example-super-long-domain-name.tld"
    long_link = (
        "https://maximov.tours/manage?"
        "order=1234567890&ticket=987654321&token="
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    return {
        "ticket": {
            "id": 987654321,
            "seat_number": "12A-ОченьДлинноеМестоБезПробеловИСКириллицей1234567890",
            "extra_baggage": 2,
        },
        "purchase": {
            "id": 123456,
            "amount_due": 1234.56,
            "payment_method": "card",
            "status": "pending",
            "customer": {
                "name": "Иван-Пётр Сергеевич",
                "email": long_email,
                "phone": "+380-50-123-45-67",
            },
        },
        "segment": {
            "departure": {"id": 1, "name": "Одесса-ГлавнаяСтанцияБезПробелов", "time": "08:15"},
            "arrival": {"id": 2, "name": "Кишинёв-ДлинноеНазваниеОстановки", "time": "11:45"},
            "duration_minutes": 210,
        },
        "route": {
            "stops": [
                {
                    "id": 1,
                    "name": "Одесса-Главная",
                    "description": "ул. Дерибасовская, 1\nПодъезд 2\nОфис 314",
                    "location": "https://maps.example.com/location/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                },
                {
                    "id": 2,
                    "name": "Кишинёв-Центр",
                    "description": "Strada Alexandru cel Bun 5\nEtaj 3\nСекция B",
                    "location": "https://maps.example.com/location/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                },
            ]
        },
        "tour": {"date": "2026-02-09"},
        "pricing": {"currency_code": "UAH", "price": 1234.56},
        "payment_status": {"status": "pending"},
        "passenger": {"name": "Иван-Пётр Сергеевич"},
        "deep_link": long_link,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render ticket template with stress-test data.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write ticket_stress.html and ticket_stress.pdf",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dto = _build_stress_dto()
    deep_link = dto.get("deep_link")

    html = render_ticket_html(dto, deep_link)
    html_path = output_dir / "ticket_stress.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_bytes = render_ticket_pdf(dto, deep_link)
    pdf_path = output_dir / "ticket_stress.pdf"
    pdf_path.write_bytes(pdf_bytes)

    print(f"Wrote {html_path}")
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
