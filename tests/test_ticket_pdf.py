import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.ticket_pdf import render_ticket_pdf


def test_render_ticket_pdf_produces_bytes():
    dto = {
        "ticket": {
            "id": 2732866,
            "seat_id": 77,
            "seat_number": 2,
            "departure_stop_id": 10,
            "arrival_stop_id": 20,
            "extra_baggage": 1,
        },
        "passenger": {"id": 5, "name": "Полонец Анна"},
        "tour": {
            "id": 42,
            "date": "2025-09-15",
            "layout_variant": 1,
            "pricelist_id": 3,
            "booking_terms": {"value": 1, "code": "EXPIRE_BEFORE_48H"},
        },
        "route": {
            "id": 7,
            "name": "Бургас — Одесса",
            "stops": [
                {
                    "id": 10,
                    "order": 1,
                    "name": "Бургас",
                    "arrival_time": None,
                    "departure_time": "12:30",
                    "description": "ул. Иван Вазов, 1",
                    "location": "https://maps.example/burgas",
                },
                {
                    "id": 20,
                    "order": 2,
                    "name": "Одесса",
                    "arrival_time": "21:30",
                    "departure_time": None,
                    "description": "пл. Старосенная, 1Б",
                    "location": "https://maps.example/odessa",
                },
            ],
        },
        "segment": {
            "departure": {"id": 10, "name": "Бургас", "order": 1, "time": "12:30"},
            "arrival": {"id": 20, "name": "Одесса", "order": 2, "time": "21:30"},
            "intermediate_stops": [],
            "duration_minutes": 690,
            "duration_human": "11h 30m",
        },
        "pricing": {"price": 2000.0, "currency_code": "UAH"},
        "purchase": {
            "id": 2690574,
            "customer": {
                "name": "Полонец Анна",
                "email": "callcenter@likebus.ua",
                "phone": "+38 (098) 343-82-82",
            },
            "amount_due": 2000.0,
            "deadline": "2025-09-10T12:00:00",
            "payment_method": "online",
            "updated_at": "2025-09-01T12:00:00",
            "status": "paid",
            "flags": {"status": "paid", "is_paid": True},
        },
        "payment_status": {"status": "paid", "is_paid": True},
    }

    deep_link = "https://client-mt.netlify.app/api/q/opaque-abc"

    pdf_bytes = render_ticket_pdf(dto, deep_link)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
