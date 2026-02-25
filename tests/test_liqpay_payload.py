import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services import liqpay


def test_build_checkout_payload_has_expected_fields(monkeypatch):
    monkeypatch.setenv("CLIENT_APP_BASE", "https://app.example.com")
    monkeypatch.setenv("LIQPAY_PUBLIC_KEY", "pub")
    monkeypatch.setenv("LIQPAY_PRIVATE_KEY", "priv")
    monkeypatch.setenv("LIQPAY_CURRENCY", "UAH")

    response = liqpay.build_checkout_payload(15, 123.456, ticket_id=77)
    payload = response["payload"]

    assert response["provider"] == "liqpay"
    assert response["checkout_form_url"] == "https://www.liqpay.ua/api/3/checkout"
    assert response["checkout_url"].startswith("https://www.liqpay.ua/api/3/checkout?data=")
    assert "&signature=" in response["checkout_url"]
    assert isinstance(response["data"], str) and response["data"]
    assert isinstance(response["signature"], str) and response["signature"]

    assert payload["version"] == "3"
    assert payload["order_id"] == "ticket-77-15"
    assert payload["description"] == "Ticket #77"
    assert payload["result_url"] == "https://app.example.com/return?purchase_id=15"
    assert payload["server_url"] == "https://app.example.com/api/public/payment/liqpay/callback"


def test_build_purchase_description_contains_full_trip_info():
    class FakeCursor:
        def execute(self, _query, _params):
            return None

        def fetchall(self):
            return [
                (date(2026, 3, 5), "Київ", "Львів"),
                (date(2026, 3, 5), "Київ", "Львів"),
                (date(2026, 3, 10), "Львів", "Київ"),
            ]

    text = liqpay.build_purchase_description(FakeCursor(), 10)

    assert text is not None
    assert "Відправлення: Київ" in text
    assert "Прибуття: Львів" in text
    assert "Дата: 05.03.2026" in text
    assert "Місць: 3" in text
    assert "Зворотна дата: 10.03.2026" in text


def test_build_checkout_payload_uses_custom_description(monkeypatch):
    monkeypatch.setenv("CLIENT_APP_BASE", "https://app.example.com")

    response = liqpay.build_checkout_payload(15, 20, description="Custom description")

    assert response["payload"]["description"] == "Custom description"
