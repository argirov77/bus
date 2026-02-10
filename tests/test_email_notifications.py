import sys
from datetime import date, time
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

sys.path.append('.')

from backend.services.email import render_ticket_email


@pytest.fixture
def email_test_env(monkeypatch):
    class DummyCursor:
        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return None

        def close(self):
            pass

    class DummyPsycopgConn:
        def __init__(self):
            self.autocommit = False

        def cursor(self):
            return DummyCursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr('psycopg2.connect', lambda *a, **k: DummyPsycopgConn())

    state = {
        "tour_date": date(2024, 1, 1),
        "stop_times": {
            1: time(8, 0),
            2: time(9, 0),
            3: time(10, 0),
            4: time(11, 0),
        },
        "stops": {
            1: "Sofia",
            2: "Plovdiv",
            3: "Varna",
            4: "Burgas",
        },
        "tickets": [],
        "purchases": {},
        "next_ticket_id": 1,
        "next_passenger_id": 1,
        "next_purchase_id": 1,
        "issue_counter": 0,
        "emails": [],
        "dto_status": "reserved",
    }

    class FakeCursor:
        def __init__(self, state):
            self.state = state
            self.last_result = None
            self.last_fetch_mode = "one"
            self.query = ""

        def execute(self, query, params=None):
            self.query = query
            q = query.lower()
            if "select route_id, pricelist_id, date from tour" in q:
                self.last_result = [1, 1, state["tour_date"]]
                self.last_fetch_mode = "one"
            elif "select route_id, date from tour" in q:
                self.last_result = [1, state["tour_date"]]
                self.last_fetch_mode = "one"
            elif "select stop_id, departure_time from routestop" in q:
                self.last_result = [
                    (1, state["stop_times"][1]),
                    (2, state["stop_times"][2]),
                    (3, state["stop_times"][3]),
                    (4, state["stop_times"][4]),
                ]
                self.last_fetch_mode = "all"
            elif "select id, available from seat" in q:
                if params:
                    state["current_seat_num"] = params[1]
                self.last_result = [1, "1234"]
                self.last_fetch_mode = "one"
            elif "select price from prices" in q:
                self.last_result = [10]
                self.last_fetch_mode = "one"
            elif "select amount_due, status from purchase" in q:
                purchase = state["purchases"].get(params[0])
                if not purchase:
                    self.last_result = None
                else:
                    self.last_result = [purchase["amount_due"], purchase["status"]]
                self.last_fetch_mode = "one"
            elif "select amount_due, customer_email from purchase" in q:
                purchase = state["purchases"].get(params[0])
                if not purchase:
                    self.last_result = None
                else:
                    self.last_result = [purchase["amount_due"], purchase["customer_email"]]
                self.last_fetch_mode = "one"
            elif "select id from ticket where purchase_id" in q:
                purchase_id = params[0]
                self.last_result = [
                    (ticket["id"],)
                    for ticket in state["tickets"]
                    if ticket["purchase_id"] == purchase_id
                ]
                self.last_fetch_mode = "all"
            elif "select t.id" in q and "from ticket" in q and "join tour" in q:
                purchase_id = params[0]
                rows = []
                for ticket in state["tickets"]:
                    if ticket["purchase_id"] == purchase_id:
                        rows.append(
                            (
                                ticket["id"],
                                ticket["purchase_id"],
                                state["tour_date"],
                                state["stop_times"][ticket["departure_stop_id"]],
                            )
                        )
                self.last_result = rows
                self.last_fetch_mode = "all"
            elif "insert into passenger" in q:
                passenger_id = state["next_passenger_id"]
                state["next_passenger_id"] += 1
                self.last_result = [passenger_id]
                self.last_fetch_mode = "one"
            elif "insert into purchase" in q:
                purchase_id = state["next_purchase_id"]
                state["next_purchase_id"] += 1
                purchase = {
                    "id": purchase_id,
                    "customer_name": params[0],
                    "customer_email": params[1],
                    "customer_phone": params[2],
                    "amount_due": params[3],
                    "status": "paid" if "'paid'" in q else "reserved",
                }
                state["purchases"][purchase_id] = purchase
                self.last_result = [purchase_id]
                self.last_fetch_mode = "one"
            elif "insert into ticket" in q:
                ticket_id = state["next_ticket_id"]
                state["next_ticket_id"] += 1
                (
                    tour_id,
                    seat_id,
                    passenger_id,
                    departure_stop_id,
                    arrival_stop_id,
                    purchase_id,
                    extra_baggage,
                ) = params
                seat_number = state.get("current_seat_num", seat_id)
                state["tickets"].append(
                    {
                        "id": ticket_id,
                        "purchase_id": purchase_id,
                        "tour_id": tour_id,
                        "seat_id": seat_id,
                        "seat_number": seat_number,
                        "departure_stop_id": departure_stop_id,
                        "arrival_stop_id": arrival_stop_id,
                    }
                )
                self.last_result = [ticket_id]
                self.last_fetch_mode = "one"
            elif "update purchase set amount_due" in q and params:
                purchase_id = params[-1]
                purchase = state["purchases"].get(purchase_id)
                if purchase:
                    purchase["amount_due"] = params[0]
                    if "status=%s" in q:
                        purchase["status"] = params[1]
            elif "update purchase set status='paid'" in q:
                purchase_id = params[0]
                purchase = state["purchases"].get(purchase_id)
                if purchase:
                    purchase["status"] = "paid"
            else:
                self.last_result = None
                self.last_fetch_mode = "one"

        def fetchone(self):
            if self.last_fetch_mode == "all":
                if not self.last_result:
                    return None
                return self.last_result[0]
            return self.last_result

        def fetchall(self):
            if self.last_fetch_mode == "all":
                return list(self.last_result)
            if self.last_result is None:
                return []
            return [self.last_result]

        def close(self):
            pass

    class FakeConn:
        def __init__(self, state):
            self.state = state
            self.closed = False

        def cursor(self):
            return FakeCursor(self.state)

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    def fake_get_connection():
        return FakeConn(state)

    def fake_issue_ticket_links(specs, lang, conn=None):
        results = []
        for spec in specs:
            state["issue_counter"] += 1
            opaque = f"opaque-{state['issue_counter']}"
            deep_link = f"https://example.test/api/q/{opaque}"
            results.append({"ticket_id": spec["ticket_id"], "deep_link": deep_link})
        return results

    def fake_send(to, subject, html_body, pdf_bytes):
        state["emails"].append(
            {
                "to": to,
                "subject": subject,
                "html": html_body,
                "pdf": pdf_bytes,
            }
        )

    def fake_get_ticket_dto(ticket_id, lang, conn):
        ticket = next((t for t in state["tickets"] if t["id"] == ticket_id), None)
        if ticket is None:
            raise ValueError("ticket not found")
        purchase = state["purchases"].get(ticket["purchase_id"])
        status = state.get("dto_status", purchase.get("status"))
        is_paid = status == "paid"
        departure_name = state["stops"].get(ticket["departure_stop_id"], "Departure")
        arrival_name = state["stops"].get(ticket["arrival_stop_id"], "Arrival")
        return {
            "ticket": {
                "id": ticket_id,
                "seat_number": ticket.get("seat_number"),
            },
            "passenger": {"name": purchase.get("customer_name")},
            "route": {"name": "Sofia — Varna"},
            "tour": {"date": state["tour_date"].isoformat()},
            "segment": {
                "departure": {"name": departure_name, "time": "08:00"},
                "arrival": {"name": arrival_name, "time": "11:00"},
            },
            "purchase": {
                "id": purchase["id"],
                "customer": {
                    "name": purchase.get("customer_name"),
                    "email": purchase.get("customer_email"),
                },
                "amount_due": purchase.get("amount_due"),
                "status": status,
                "flags": {"status": status, "is_paid": is_paid},
                "payment_method": "online",
            },
            "payment_status": {"status": status, "is_paid": is_paid},
        }

    class DummyQR:
        def __init__(self, *args, **kwargs):
            pass

        def add_data(self, *args, **kwargs):
            pass

        def make(self, *args, **kwargs):
            pass

        def make_image(self, *args, **kwargs):
            class DummyImage:
                def save(self, buffer, format="PNG"):
                    buffer.write(b"")

            return DummyImage()

    class DummyHTML:
        def __init__(self, *args, **kwargs):
            pass

        def write_pdf(self):
            return b"%PDF%"

    monkeypatch.setitem(sys.modules, 'qrcode', SimpleNamespace(QRCode=DummyQR))
    monkeypatch.setitem(sys.modules, 'weasyprint', SimpleNamespace(HTML=DummyHTML))

    from backend.routers import purchase as purchase_router

    monkeypatch.setattr(purchase_router, 'get_connection', fake_get_connection)
    monkeypatch.setattr(purchase_router, 'issue_ticket_links', fake_issue_ticket_links)
    monkeypatch.setattr(purchase_router, 'render_ticket_pdf', lambda dto, deep_link: b'%PDF-FAKE%')
    monkeypatch.setattr(purchase_router, 'send_ticket_email', fake_send)
    monkeypatch.setattr(purchase_router, 'get_ticket_dto', fake_get_ticket_dto)

    return state, purchase_router


@pytest.mark.parametrize(
    "lang, expected_subject, marker",
    [
        ("en", "Your ticket #42", "Open your ticket online"),
        ("bg", "Вашият билет №42", "Отворете билета онлайн"),
        ("ua", "Ваш квиток №42", "Відкрити квиток онлайн"),
    ],
)
def test_render_ticket_email_localization(lang, expected_subject, marker):
    dto = {
        "ticket": {"id": 42, "seat_number": 7},
        "passenger": {"name": "Ivan"},
        "route": {"name": "Sofia — Varna"},
        "tour": {"date": "2024-01-01"},
        "segment": {
            "departure": {"name": "Sofia", "time": "08:00"},
            "arrival": {"name": "Varna", "time": "11:00"},
        },
        "purchase": {
            "id": 99,
            "customer": {"name": "Ivan", "email": "ivan@example.com"},
            "amount_due": 15.5,
            "status": "reserved",
            "flags": {"status": "reserved", "is_paid": False},
        },
    }
    deep_link = "https://example.test/api/q/opaque-42"

    subject, html = render_ticket_email(dto, deep_link, lang)

    assert expected_subject in subject
    assert deep_link in html
    assert marker in html


def _run_background_tasks(tasks: BackgroundTasks) -> None:
    for task in tasks.tasks:
        task.func(*task.args, **task.kwargs)


def test_create_purchase_sends_email(email_test_env):
    state, purchase_router = email_test_env

    data = purchase_router.PurchaseCreate(
        tour_id=1,
        seat_nums=[1],
        passenger_names=["Alice"],
        passenger_phone="123",
        passenger_email="alice@example.com",
        departure_stop_id=1,
        arrival_stop_id=3,
        adult_count=1,
        discount_count=0,
        lang="en",
    )
    tasks = BackgroundTasks()

    purchase_router.create_purchase(data, background_tasks=tasks)
    assert tasks.tasks, "Expected background email task to be scheduled"

    _run_background_tasks(tasks)

    emails = state["emails"]
    assert len(emails) == 1
    email = emails[0]
    assert email["to"] == "alice@example.com"
    assert email["pdf"] == b"%PDF-FAKE%"
    assert "https://example.test/api/q/opaque-1" in email["html"]
    assert "Your ticket" in email["subject"]


def test_pay_booking_sends_payment_confirmation(email_test_env):
    state, purchase_router = email_test_env

    data = purchase_router.PurchaseCreate(
        tour_id=1,
        seat_nums=[1],
        passenger_names=["Alice"],
        passenger_phone="123",
        passenger_email="alice@example.com",
        departure_stop_id=1,
        arrival_stop_id=3,
        adult_count=1,
        discount_count=0,
        lang="en",
    )
    initial_tasks = BackgroundTasks()
    purchase_router.create_purchase(data, background_tasks=initial_tasks)
    _run_background_tasks(initial_tasks)

    state["emails"].clear()
    state["dto_status"] = "paid"

    pay_tasks = BackgroundTasks()
    scope = {"type": "http", "headers": [], "query_string": b""}
    request = Request(scope)
    request.state.is_admin = True

    pay_in = purchase_router.PayIn(purchase_id=1)
    purchase_router.pay_booking(
        pay_in,
        request,
        background_tasks=pay_tasks,
        context=SimpleNamespace(),
    )

    assert pay_tasks.tasks, "Expected payment email task"
    _run_background_tasks(pay_tasks)

    emails = state["emails"]
    assert len(emails) == 1
    email = emails[0]
    confirmation_markers = [
        "(payment confirmed)",
        "(плащането е потвърдено)",
        "(оплату підтверджено)",
    ]
    assert any(marker in email["html"] for marker in confirmation_markers)
    assert "https://example.test/api/q/opaque-2" in email["html"]
    assert email["pdf"] == b"%PDF-FAKE%"
