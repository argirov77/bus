from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from backend.services.ticket_pdf import render_ticket_html, render_ticket_pdf


def main() -> None:
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    deep_link = (
        "https://example.com/manage/"
        "this-is-a-very-long-link-without-spaces-"
        "and-it-keeps-going-to-test-overflow-behavior-"
        "?order=1234567890&token=abcdefghijklmnopqrstuvwxyz0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )

    dto = {
        "i18n": {
            "brand_name": "Максимов Турс",
            "manage_online_button": "Управлять поездкой",
        },
        "tour": {"date": "2026-02-09"},
        "segment": {
            "duration_minutes": 615,
            "departure": {
                "id": "dep-stop",
                "name": "Очень-длинное-название-станции-отправления-без-пробелов"
                "которое-нужно-переносить",
                "time": "12:03",
            },
            "arrival": {
                "id": "arr-stop",
                "name": "Констанца",
                "time": "13:10",
            },
        },
        "route": {
            "stops": [
                {
                    "id": "dep-stop",
                    "name": "Болград",
                    "description": (
                        "Поворот на трассе Е95, возле АЗС\n"
                        "Длинный адрес с переносами и кириллицей, "
                        "который должен корректно переноситься в несколько строк"
                    ),
                    "location": "https://maps.example.com/very/long/path",
                },
                {
                    "id": "arr-stop",
                    "name": "Констанца",
                    "description": (
                        "OMV Заправка, улица Очень Длинная, дом 123456, "
                        "подъезд 7, этаж 12, офис 999\n"
                        "Еще одна строка адреса для стресс-теста"
                    ),
                    "location": "https://maps.example.com/another/very/long/path",
                },
            ]
        },
        "ticket": {
            "id": "TICKET-2026-00000000000000000001",
            "seat_number": "12A-ОченьДлинныйНомерМеста",
            "extra_baggage": 2,
        },
        "purchase": {
            "id": "ORDER-0000000000000000000001",
            "amount_due": "1999.99",
            "payment_method": "Карта Visa/Mastercard",
            "customer": {
                "name": "Дмитрий\nСтойков",
                "email": "verylongemailaddresswithoutbreaks"
                "andwithmanychars@exampleveryveryverylongdomain.com",
                "phone": "+380-553-252-3523-EXT-9999",
            },
            "flags": {"status": "paid"},
        },
        "pricing": {"currency_code": "UAH"},
    }

    html = render_ticket_html(dto, deep_link)
    (output_dir / "ticket_stress.html").write_text(html, encoding="utf-8")

    pdf_bytes = render_ticket_pdf(dto, deep_link)
    (output_dir / "ticket_stress.pdf").write_bytes(pdf_bytes)


if __name__ == "__main__":
    main()
