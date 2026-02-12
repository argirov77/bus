import os
import sys

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
    assert payload["result_url"] == "https://app.example.com/purchase/15"
