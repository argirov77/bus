from typing import List


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
