"""Helpers for generating debug/stress ticket data."""

from __future__ import annotations

from typing import Any, Dict


def build_stress_ticket_dto() -> Dict[str, Any]:
    long_email = (
        "verylongemailaddresswithmultiplesectionsandtags"
        "+stress-test-1234567890"
        "@example-super-long-domain-name-with-many-parts.tld"
    )
    long_link = (
        "https://client.maximov.tours/api/q/"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        "?utm_source=stress_test&token=longtokenvalue"
    )
    long_address = (
        "УкраинаОдесскаяОбластьГородОдесса"
        "ОченьДлинноеНазваниеУлицыБезПробелов"
        "Дом123Квартира456Подъезд7Этаж89"
    )
    return {
        "ticket": {
            "id": "TKT-999999999999999999999999",
            "seat_number": "12A-ОченьДлинноеМестоБезПробеловИСКириллицей1234567890",
            "extra_baggage": 3,
        },
        "purchase": {
            "id": "ORD-888888888888888888888888",
            "amount_due": 98765.43,
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
                    "description": long_address,
                    "location": "https://maps.example.com/location/" + "a" * 80,
                },
                {
                    "id": 2,
                    "name": "Кишинёв-Центр",
                    "description": "StradaAlexandruCelBun5Etaj3SectorBбезпробелов",
                    "location": "https://maps.example.com/location/" + "b" * 80,
                },
            ]
        },
        "tour": {"date": "2026-02-09"},
        "pricing": {"currency_code": "UAH", "price": 98765.43},
        "payment_status": {"status": "pending"},
        "passenger": {"name": "Иван-Пётр Сергеевич"},
        "deep_link": long_link,
    }
