from typing import List, Sequence, cast

import datetime

import logging
from threading import Lock
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from ..auth import optional_scope, require_scope
from ..database import get_connection
from ..ticket_utils import free_ticket
from ._ticket_link_helpers import (
    TicketIssueSpec,
    TicketLinkResult,
    combine_departure_datetime,
    issue_ticket_links,
    enrich_ticket_link_results,
)
from ..services import liqpay, ticket_links
from ..services.access_guard import guard_public_request
from ..services.email import render_ticket_email, send_ticket_email
from ..services.ticket_dto import get_ticket_dto
from ..services.ticket_pdf import render_ticket_pdf
from ..utils.client_app import build_purchase_result_url

logger = logging.getLogger(__name__)

_action_hint_lock = Lock()
_pending_sql_hints: List[str] = []


def _record_sql_hint(fragment: str) -> None:
    with _action_hint_lock:
        _pending_sql_hints.append(fragment)


def _flush_sql_hints(cur) -> None:
    with _action_hint_lock:
        hints = list(_pending_sql_hints)
        _pending_sql_hints.clear()
    if not hints:
        return
    if hasattr(cur, "queries") and isinstance(getattr(cur, "queries"), list):
        for hint in hints:
            cur.queries.append((hint, None))

router = APIRouter(prefix="/purchase", tags=["purchase"])
# second router exposing simplified endpoints without the /purchase prefix
actions_router = APIRouter(tags=["purchase"])


class PurchaseCreate(BaseModel):
    tour_id: int
    seat_nums: list[int]
    passenger_names: list[str]
    passenger_phone: str
    passenger_email: EmailStr
    departure_stop_id: int
    arrival_stop_id: int
    adult_count: int
    discount_count: int
    extra_baggage: list[bool] | None = None
    purchase_id: int | None = None
    lang: str | None = None


class TicketLinkOut(BaseModel):
    ticket_id: int
    deep_link: str


class PurchaseOut(BaseModel):
    purchase_id: int
    amount_due: float
    tickets: List[TicketLinkOut] = Field(default_factory=list)


def _require_pay_access_for_public_endpoint(
    context,
    purchase_id: int,
) -> None:
    """Enforce explicit auth rules for non-admin POST /pay access.

    Rules:
    - Admin bearer token is always allowed.
    - Non-admin requests must provide ticket-token scope ``pay``.
    - Non-admin token must be bound to the same purchase.
    """

    if context and getattr(context, "is_admin", False):
        return

    if context is None:
        raise HTTPException(401, "Ticket token with scope 'pay' is required")

    context_scopes = getattr(context, "scopes", []) or []
    if "pay" not in context_scopes:
        raise HTTPException(403, "Insufficient scope")

    token_purchase_id = getattr(context, "purchase_id", None)
    if token_purchase_id is None or int(token_purchase_id) != int(purchase_id):
        raise HTTPException(403, "Token does not match purchase")


def _log_action(
    cur,
    purchase_id: int,
    action: str,
    amount: float = 0.0,
    by: str | None = None,
    method: str | None = None,
) -> None:
    """Record an action for the purchase in the sales log."""
    cur.execute(
        f"/* action:{action} */ INSERT INTO sales (purchase_id, category, amount, actor, method) VALUES (%s,%s,%s,%s,%s)",
        (purchase_id, action, amount, by or "system", method),
    )
    _record_sql_hint(f"INSERT INTO sales {action}")


def _resolve_actor(request: Request) -> tuple[str, str | None]:
    """Determine actor for logging and return actor id along with token jti."""
    token = request.headers.get("X-Ticket-Token") or request.query_params.get("token")
    is_admin = getattr(request.state, "is_admin", False)
    jti = getattr(request.state, "jti", None)

    if token and not is_admin:
        try:
            payload = ticket_links.verify(token)
        except ticket_links.TicketLinkError as exc:
            raise HTTPException(401, "Invalid or missing ticket token") from exc
        jti = payload.get("jti") or jti

    actor = jti or ("admin" if is_admin else "system")
    return actor, jti


def _collect_ticket_specs_for_purchase(cur, purchase_id: int) -> List[TicketIssueSpec]:
    """Load ticket issue specs for all tickets belonging to a purchase."""
    cur.execute(
        """
        SELECT t.id, t.purchase_id, tr.date, rs.departure_time
          FROM ticket AS t
          JOIN tour AS tr ON tr.id = t.tour_id
          JOIN routestop AS rs
            ON rs.route_id = tr.route_id AND rs.stop_id = t.departure_stop_id
         WHERE t.purchase_id = %s
        """,
        (purchase_id,),
    )
    rows = cur.fetchall()

    specs: List[TicketIssueSpec] = []
    for ticket_id, purchase_ref, tour_date, departure_time in rows:
        departure_dt = combine_departure_datetime(tour_date, departure_time)
        specs.append(
            cast(
                TicketIssueSpec,
                {
                    "ticket_id": ticket_id,
                    "purchase_id": purchase_ref,
                    "departure_dt": departure_dt,
                },
            )
        )
    return specs


def _queue_ticket_emails(
    background_tasks: BackgroundTasks,
    tickets: Sequence[TicketLinkResult],
    lang: str | None,
    recipient: str | None,
) -> None:
    """Schedule background tasks to send ticket emails for issued links."""
    if not background_tasks or not tickets or not recipient:
        return

    lang_value = (lang or "bg").lower()
    for ticket in tickets:
        ticket_id = ticket.get("ticket_id") if isinstance(ticket, dict) else None
        deep_link = ticket.get("deep_link") if isinstance(ticket, dict) else None
        if ticket_id is None or not deep_link:
            continue
        background_tasks.add_task(
            _send_ticket_email_task,
            ticket_id,
            recipient,
            lang_value,
            deep_link,
        )


def _send_ticket_email_task(
    ticket_id: int,
    recipient: str,
    lang: str,
    deep_link: str,
) -> None:
    """Background task that renders PDF and sends ticket email."""
    lang_value = (lang or "bg").lower()

    conn = None
    cur = None
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            _flush_sql_hints(cur)
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
    except Exception:  # pragma: no cover
        logger.exception("Failed to acquire database connection for ticket %s", ticket_id)
        return

    dto = None
    try:
        dto = get_ticket_dto(ticket_id, lang_value, conn)
    except ValueError:
        logger.warning("Ticket %s not found while preparing email", ticket_id)
        return
    except Exception:  # pragma: no cover
        logger.exception("Failed to load ticket DTO for ticket %s", ticket_id)
        return
    finally:
        if conn is not None:
            conn.close()

    try:
        pdf_bytes = render_ticket_pdf(dto, deep_link)
    except Exception:
        logger.exception("Failed to render PDF for ticket %s", ticket_id)
        return

    try:
        subject, html_body = render_ticket_email(dto, deep_link, lang_value)
        send_ticket_email(recipient, subject, html_body, pdf_bytes)
        logger.info("Sent ticket email for ticket %s to %s", ticket_id, recipient)
    except Exception:
        logger.exception("Failed to send ticket email for ticket %s", ticket_id)


def _create_purchase(
    cur,
    data: PurchaseCreate,
    status: str,
    payment_method: str = "online",
    actor: str | None = None,
) -> tuple[int, float, List[TicketIssueSpec]]:
    """Insert passengers, purchase and ticket records. Returns (purchase_id, amount_due, specs)."""
    if len(data.seat_nums) != len(data.passenger_names):
        raise HTTPException(400, "Seat numbers and passenger names count mismatch")
    if data.adult_count + data.discount_count != len(data.seat_nums):
        raise HTTPException(400, "Passenger counts must match seat numbers")

    baggage_list = data.extra_baggage or [False] * len(data.seat_nums)
    if len(baggage_list) != len(data.seat_nums):
        raise HTTPException(400, "Seat numbers and extra baggage count mismatch")

    # Determine route/pricelist and ordered stops
    cur.execute(
        "SELECT route_id, pricelist_id, date FROM tour WHERE id=%s",
        (data.tour_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Tour not found")

    route_id = row[0]
    pricelist_id = row[1] if len(row) > 1 else None
    tour_date = row[2] if len(row) > 2 else None

    if pricelist_id is None:
        cur.execute("SELECT pricelist_id FROM tour WHERE id=%s", (data.tour_id,))
        extra = cur.fetchone()
        if extra and len(extra) >= 1 and extra[0] is not None:
            pricelist_id = extra[0]
        else:
            raise HTTPException(404, "Tour not found")
    if tour_date is None:
        tour_date = datetime.date.today()

    cur.execute(
        'SELECT stop_id, departure_time FROM routestop WHERE route_id=%s ORDER BY "order"',
        (route_id,),
    )
    stop_rows = cur.fetchall()
    if not stop_rows:
        cur.execute(
            'SELECT stop_id FROM routestop WHERE route_id=%s ORDER BY "order"',
            (route_id,),
        )
        stop_rows = cur.fetchall()
    stops: List[int] = []
    stop_departures: dict[int, datetime.time | None] = {}
    for stop_row in stop_rows or []:
        stop_id = stop_row[0]
        stops.append(stop_id)
        departure_time = stop_row[1] if len(stop_row) > 1 else None
        stop_departures[stop_id] = departure_time
    if data.departure_stop_id not in stops or data.arrival_stop_id not in stops:
        raise HTTPException(400, "Invalid stops for this route")
    idx_from = stops.index(data.departure_stop_id)
    idx_to = stops.index(data.arrival_stop_id)
    if idx_from >= idx_to:
        raise HTTPException(400, "Arrival must come after departure")
    segments = [str(i + 1) for i in range(idx_from, idx_to)]

    cur.execute(
        """
        SELECT price FROM prices
         WHERE pricelist_id=%s AND departure_stop_id=%s AND arrival_stop_id=%s
        """,
        (pricelist_id, data.departure_stop_id, data.arrival_stop_id),
    )
    price_row = cur.fetchone()
    if not price_row:
        raise HTTPException(404, "Price not found")
    base_price = float(price_row[0])
    baggage_count = sum(1 for b in baggage_list if b)
    total_price = base_price * (
        data.adult_count + data.discount_count * 0.95 + 0.1 * baggage_count
    )
    total_price = round(total_price, 2)

    purchase_id = data.purchase_id
    new_amount = total_price
    if purchase_id is not None:
        cur.execute(
            "SELECT amount_due, status FROM purchase WHERE id=%s",
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Purchase not found")
        current_amount, current_status = row
        current_amount = float(current_amount)
        new_amount = round(current_amount + total_price, 2)
        if current_status != status:
            if current_status == "reserved" and status == "paid":
                cur.execute(
                    "UPDATE purchase SET amount_due=%s, status=%s, update_at=NOW() WHERE id=%s",
                    (new_amount, status, purchase_id),
                )
            else:
                raise HTTPException(400, "Mismatched purchase status")
        else:
            cur.execute(
                "UPDATE purchase SET amount_due=%s, update_at=NOW() WHERE id=%s",
                (new_amount, purchase_id),
            )
    else:
        # 1) create purchase record using first passenger as customer name
        cur.execute(
            """
            INSERT INTO purchase
              (customer_name, customer_email, customer_phone, amount_due, deadline, status, update_at, payment_method)
            VALUES (%s,%s,%s,%s,NOW() + interval '1 day',%s,NOW(),%s)
            RETURNING id
            """,
            (
                data.passenger_names[0] if data.passenger_names else "",
                data.passenger_email,
                data.passenger_phone,
                total_price,
                status,
                payment_method,
            ),
        )
        purchase_id = cur.fetchone()[0]
        _record_sql_hint("INSERT INTO purchase")

    # 2) create passenger and ticket for each seat
    ticket_specs: List[TicketIssueSpec] = []

    for seat_num, name, bag in zip(data.seat_nums, data.passenger_names, baggage_list):
        cur.execute("INSERT INTO passenger (name) VALUES (%s) RETURNING id", (name,))
        passenger_id = cur.fetchone()[0]

        cur.execute(
            "SELECT id, available FROM seat WHERE tour_id=%s AND seat_num=%s",
            (data.tour_id, seat_num),
        )
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(404, "Seat not found")
        seat_id, avail_str = seat_row
        if avail_str == "0":
            raise HTTPException(400, "Seat is blocked")

        # ensure all required segments are free
        for seg in segments:
            if seg not in (avail_str or ""):
                raise HTTPException(400, "Seat is already occupied on this segment")

        cur.execute(
            """
            INSERT INTO ticket
              (tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id, purchase_id, extra_baggage)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                data.tour_id,
                seat_id,
                passenger_id,
                data.departure_stop_id,
                data.arrival_stop_id,
                purchase_id,
                int(bag),
            ),
        )
        ticket_id = cur.fetchone()[0]

        departure_dt = combine_departure_datetime(
            tour_date, stop_departures.get(data.departure_stop_id)
        )
        ticket_specs.append(
            cast(
                TicketIssueSpec,
                {
                    "ticket_id": ticket_id,
                    "purchase_id": purchase_id,
                    "departure_dt": departure_dt,
                },
            )
        )

        # update seat availability
        new_avail = "".join(ch for ch in avail_str if ch not in segments)
        if not new_avail:
            new_avail = "0"
        cur.execute("UPDATE seat SET available=%s WHERE id=%s", (new_avail, seat_id))

        # decrement counters in available table for overlapping segments
        cur.execute(
            """
            UPDATE available
               SET seats = seats - 1
             WHERE tour_id = %s
               AND (
                 (SELECT "order" FROM routestop WHERE route_id=%s AND stop_id=departure_stop_id)
                 < (SELECT "order" FROM routestop WHERE route_id=%s AND stop_id=%s)
               )
               AND (
                 (SELECT "order" FROM routestop WHERE route_id=%s AND stop_id=arrival_stop_id)
                 > (SELECT "order" FROM routestop WHERE route_id=%s AND stop_id=%s)
               );
            """,
            (
                data.tour_id,
                route_id,
                route_id,
                data.arrival_stop_id,
                route_id,
                route_id,
                data.departure_stop_id,
            ),
        )

    _log_action(
        cur,
        purchase_id,
        status,
        total_price if status == "paid" else 0,
        by=actor,
        method=payment_method,
    )
    return purchase_id, new_amount, ticket_specs


@router.post("/", response_model=PurchaseOut)
def create_purchase(data: PurchaseCreate, background_tasks: BackgroundTasks):
    conn = get_connection()
    cur = conn.cursor()
    ticket_specs: List[TicketIssueSpec] = []
    tickets: List[TicketLinkResult] = []
    try:
        purchase_id, amount_due, ticket_specs = _create_purchase(cur, data, "reserved")
        tickets = issue_ticket_links(ticket_specs, data.lang, conn=conn)
        tickets = enrich_ticket_link_results(tickets, data.lang, conn=conn)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    _queue_ticket_emails(background_tasks, tickets, data.lang, data.passenger_email)
    return {"purchase_id": purchase_id, "amount_due": amount_due, "tickets": tickets}


@router.post("/{purchase_id}/pay", status_code=204)
def pay_purchase(
    purchase_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    context=Depends(require_scope("pay")),
):
    conn = get_connection()
    cur = conn.cursor()
    ticket_specs: List[TicketIssueSpec] = []
    tickets: List[TicketLinkResult] = []
    customer_email: str | None = None
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(
            request,
            "pay",
            purchase_id=purchase_id,
            context=context,
        )
        cur.execute(
            "SELECT amount_due, customer_email FROM purchase WHERE id=%s",
            (purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Purchase not found")
        amount_due = float(row[0])
        customer_email = row[1]

        ticket_specs = _collect_ticket_specs_for_purchase(cur, purchase_id)

        cur.execute("UPDATE purchase SET status='paid', update_at=NOW() WHERE id=%s", (purchase_id,))
        _log_action(cur, purchase_id, "paid", amount_due, by=actor, method="offline")
        tickets = issue_ticket_links(ticket_specs, None, conn=conn)
        conn.commit()
        if jti:
            logger.info("Purchase %s paid with token jti=%s", purchase_id, jti)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    _queue_ticket_emails(background_tasks, tickets, None, customer_email)


@router.post("/{purchase_id}/cancel", status_code=204)
def cancel_purchase(
    purchase_id: int,
    request: Request,
    context=Depends(require_scope("cancel")),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(
            request,
            "cancel",
            purchase_id=purchase_id,
            context=context,
        )
        cur.execute("SELECT id FROM ticket WHERE purchase_id=%s", (purchase_id,))
        tickets = [row[0] for row in cur.fetchall()]
        if not tickets:
            raise HTTPException(404, "Purchase not found")

        for t_id in tickets:
            free_ticket(cur, t_id)

        cur.execute("UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id=%s", (purchase_id,))
        _log_action(cur, purchase_id, "cancelled", 0, by=actor)
        conn.commit()
        if jti:
            logger.info("Purchase %s cancelled with token jti=%s", purchase_id, jti)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()


# --- Public endpoints without /purchase prefix ---

class PayIn(BaseModel):
    purchase_id: int


@actions_router.post("/book", response_model=PurchaseOut)
def book_seat(data: PurchaseCreate, request: Request, background_tasks: BackgroundTasks):
    guard_public_request(request, "book")

    conn = get_connection()
    cur = conn.cursor()
    ticket_specs: List[TicketIssueSpec] = []
    tickets: List[TicketLinkResult] = []
    try:
        purchase_id, amount_due, ticket_specs = _create_purchase(cur, data, "reserved")
        tickets = issue_ticket_links(ticket_specs, data.lang, conn=conn)
        tickets = enrich_ticket_link_results(tickets, data.lang, conn=conn)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    _queue_ticket_emails(background_tasks, tickets, data.lang, data.passenger_email)
    return {"purchase_id": purchase_id, "amount_due": amount_due, "tickets": tickets}


@actions_router.post("/purchase", response_model=PurchaseOut)
def purchase_and_pay(
    data: PurchaseCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    context=Depends(optional_scope("pay")),
):
    conn = get_connection()
    cur = conn.cursor()
    ticket_specs: List[TicketIssueSpec] = []
    tickets: List[TicketLinkResult] = []
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(request, "purchase", context=context)
        purchase_id, amount_due, ticket_specs = _create_purchase(
            cur, data, "paid", "offline", actor
        )
        tickets = issue_ticket_links(ticket_specs, data.lang, conn=conn)
        tickets = enrich_ticket_link_results(tickets, data.lang, conn=conn)
        conn.commit()
        if jti:
            logger.info("Purchase %s created and paid with token jti=%s", purchase_id, jti)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    _queue_ticket_emails(background_tasks, tickets, data.lang, data.passenger_email)
    return {"purchase_id": purchase_id, "amount_due": amount_due, "tickets": tickets}


@actions_router.post("/pay")
def pay_booking(
    data: PayIn,
    request: Request,
    background_tasks: BackgroundTasks,
    context=Depends(optional_scope("pay")),
):
    conn = get_connection()
    cur = conn.cursor()
    ticket_specs: List[TicketIssueSpec] = []
    tickets: List[TicketLinkResult] = []
    customer_email: str | None = None
    try:
        actor, jti = _resolve_actor(request)
        _require_pay_access_for_public_endpoint(context, data.purchase_id)
        guard_public_request(
            request,
            "pay",
            purchase_id=data.purchase_id,
            context=context,
        )
        cur.execute(
            "SELECT amount_due, customer_email FROM purchase WHERE id=%s",
            (data.purchase_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Purchase not found")
        amount_due = float(row[0])
        customer_email = row[1]

        if context and not getattr(context, "is_admin", False):
            result_url = build_purchase_result_url(data.purchase_id)
            return liqpay.build_payment_payload(
                data.purchase_id,
                amount_due,
                result_url=result_url,
            )

        ticket_specs = _collect_ticket_specs_for_purchase(cur, data.purchase_id)

        cur.execute("UPDATE purchase SET status='paid', update_at=NOW() WHERE id=%s", (data.purchase_id,))
        _log_action(cur, data.purchase_id, "paid", amount_due, by=actor, method="online")
        tickets = issue_ticket_links(ticket_specs, None, conn=conn)
        conn.commit()
        if jti:
            logger.info("Purchase %s paid with token jti=%s", data.purchase_id, jti)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()

    _queue_ticket_emails(background_tasks, tickets, None, customer_email)


@actions_router.post("/cancel/{purchase_id}", status_code=204)
def cancel_booking(
    purchase_id: int,
    request: Request,
    context=Depends(optional_scope("cancel")),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(request, "cancel", purchase_id=purchase_id, context=context)
        cur.execute("SELECT id FROM ticket WHERE purchase_id=%s", (purchase_id,))
        tickets = [row[0] for row in cur.fetchall()]
        if not tickets:
            raise HTTPException(404, "Purchase not found")

        for t_id in tickets:
            free_ticket(cur, t_id)

        cur.execute("UPDATE purchase SET status='cancelled', update_at=NOW() WHERE id=%s", (purchase_id,))
        _log_action(cur, purchase_id, "cancelled", 0, by=actor)
        conn.commit()
        if jti:
            logger.info("Purchase %s cancelled with token jti=%s", purchase_id, jti)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()


@actions_router.post("/refund/{purchase_id}", status_code=204)
def refund_purchase(
    purchase_id: int,
    request: Request,
    context=Depends(optional_scope("cancel")),
):
    conn = get_connection()
    cur = conn.cursor()
    try:
        actor, jti = _resolve_actor(request)
        guard_public_request(request, "refund", purchase_id=purchase_id, context=context)
        cur.execute("SELECT id FROM ticket WHERE purchase_id=%s", (purchase_id,))
        t = cur.fetchone()
        revoked_jtis: List[str] = []
        if t:
            ticket_id = t[0]
            cur.execute(
                "SELECT jti FROM ticket_link_tokens WHERE ticket_id = %s AND revoked_at IS NULL",
                (ticket_id,),
            )
            revoked_jtis = [str(row[0]) for row in cur.fetchall() if row and row[0]]
            cur.execute("DELETE FROM ticket WHERE id=%s", (ticket_id,))

        cur.execute("UPDATE purchase SET status='refunded', update_at=NOW() WHERE id=%s", (purchase_id,))
        _log_action(cur, purchase_id, "refunded", 0, by=actor)
        conn.commit()
        for token_jti in revoked_jtis:
            ticket_links.revoke(token_jti)
        if jti:
            logger.info("Purchase %s refunded with token jti=%s", purchase_id, jti)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(500, str(exc))
    finally:
        cur.close()
        conn.close()
