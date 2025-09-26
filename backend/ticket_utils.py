import logging
from typing import List, Tuple

from .services import ticket_links


logger = logging.getLogger(__name__)


def free_ticket(cur, ticket_id: int) -> None:
    """Free seat availability and remove ticket record.

    Restores seat.available segments and increases counters in the
    available table for the segments covered by the ticket.
    """
    # Fetch ticket details
    cur.execute(
        """
        SELECT tour_id, seat_id, departure_stop_id, arrival_stop_id
          FROM ticket
         WHERE id = %s
        """,
        (ticket_id,),
    )
    row = cur.fetchone()
    if not row:
        return
    tour_id, seat_id, dep, arr = row

    cur.execute(
        "SELECT jti FROM ticket_link_tokens WHERE ticket_id = %s AND revoked_at IS NULL",
        (ticket_id,),
    )
    token_rows = cur.fetchall()
    jtis = [str(token[0]) for token in token_rows if token and token[0]]

    # Resolve route and ordered stops
    cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
    r = cur.fetchone()
    if not r:
        return
    route_id = r[0]

    cur.execute(
        """
        SELECT stop_id FROM routestop
         WHERE route_id = %s
         ORDER BY "order"
        """,
        (route_id,),
    )
    stops = [s[0] for s in cur.fetchall()]
    if dep not in stops or arr not in stops:
        return
    idx_from = stops.index(dep)
    idx_to = stops.index(arr)
    if idx_from >= idx_to:
        return
    segments: List[str] = [str(i + 1) for i in range(idx_from, idx_to)]

    # Restore seat.available string
    cur.execute("SELECT available FROM seat WHERE id = %s", (seat_id,))
    seat_row = cur.fetchone()
    old_avail = seat_row[0] if seat_row and seat_row[0] else ""
    merged = sorted(set(old_avail + "".join(segments)), key=int)
    new_avail = "".join(merged) if merged else "0"
    cur.execute(
        "UPDATE seat SET available = %s WHERE id = %s",
        (new_avail, seat_id),
    )

    # Increment available.seats for each overlapping segment
    for i in range(idx_from, idx_to):
        d, a = stops[i], stops[i + 1]
        cur.execute(
            """
            UPDATE available
               SET seats = seats + 1
             WHERE tour_id = %s
               AND departure_stop_id = %s
               AND arrival_stop_id = %s
            """,
            (tour_id, d, a),
        )

    # Remove the ticket itself
    cur.execute("DELETE FROM ticket WHERE id = %s", (ticket_id,))

    for jti in jtis:
        try:
            ticket_links.revoke(jti)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to revoke ticket link token %s", jti)


def recalc_available(cur, tour_id: int) -> None:
    """Rebuild the available table for a tour based on seat availability."""
    cur.execute(
        "SELECT route_id, pricelist_id FROM tour WHERE id=%s", (tour_id,)
    )
    row = cur.fetchone()
    if not row:
        return
    route_id, pricelist_id = row

    cur.execute(
        'SELECT stop_id FROM routestop WHERE route_id=%s ORDER BY "order"',
        (route_id,),
    )
    stops = [r[0] for r in cur.fetchall()]
    if len(stops) < 2:
        return

    cur.execute(
        "SELECT seat_num, available FROM seat WHERE tour_id=%s",
        (tour_id,),
    )
    seats: List[Tuple[int, str]] = cur.fetchall()

    # drop previous counters
    cur.execute("DELETE FROM available WHERE tour_id=%s", (tour_id,))

    cur.execute(
        "SELECT departure_stop_id, arrival_stop_id FROM prices WHERE pricelist_id=%s",
        (pricelist_id,),
    )
    valid_segments = cur.fetchall()

    for dep, arr in valid_segments:
        if dep not in stops or arr not in stops:
            continue
        i_from = stops.index(dep)
        i_to = stops.index(arr)
        if i_from >= i_to:
            continue
        required = [str(i + 1) for i in range(i_from, i_to)]
        count = sum(
            1 for _, avail in seats if avail and all(seg in avail for seg in required)
        )
        cur.execute(
            "INSERT INTO available (tour_id, departure_stop_id, arrival_stop_id, seats) VALUES (%s,%s,%s,%s)",
            (tour_id, dep, arr, count),
        )
