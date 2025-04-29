# backend/app/routers/ticket.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import List
from database import get_connection

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketCreate(BaseModel):
    tour_id: int
    seat_num: int
    passenger_name: str
    passenger_phone: str
    passenger_email: EmailStr
    departure_stop_id: int
    arrival_stop_id: int


class TicketOut(BaseModel):
    ticket_id: int


class TicketReassign(BaseModel):
    tour_id:   int
    from_seat: int
    to_seat:   int


@router.post("/", response_model=TicketOut)
def create_ticket(data: TicketCreate):
    # … your existing implementation unchanged …
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1) verify tour
        cur.execute("SELECT route_id FROM tour WHERE id = %s", (data.tour_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Tour not found")
        route_id = row[0]

        # 2) find seat & availability
        cur.execute(
            "SELECT id, available FROM seat WHERE tour_id = %s AND seat_num = %s",
            (data.tour_id, data.seat_num),
        )
        seat_row = cur.fetchone()
        if not seat_row:
            raise HTTPException(404, "Seat not found")
        seat_id, avail_str = seat_row

        if avail_str == "0":
            raise HTTPException(400, "Seat is blocked")

        # 3) load route stops
        cur.execute(
            "SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\"",
            (route_id,),
        )
        stops = [r[0] for r in cur.fetchall()]
        if data.departure_stop_id not in stops or data.arrival_stop_id not in stops:
            raise HTTPException(400, "Invalid stops for this route")

        idx_from = stops.index(data.departure_stop_id)
        idx_to   = stops.index(data.arrival_stop_id)
        if idx_from >= idx_to:
            raise HTTPException(400, "Arrival must come after departure")

        # 4) build segments
        segments = [str(i + 1) for i in range(idx_from, idx_to)]

        # 5) ensure all segments free
        for seg in segments:
            if seg not in avail_str:
                raise HTTPException(400, "Seat is already occupied on this segment")

        # 6) insert passenger
        cur.execute(
            """
            INSERT INTO passenger (name, phone, email)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (data.passenger_name, data.passenger_phone, data.passenger_email),
        )
        passenger_id = cur.fetchone()[0]

        # 7) insert ticket
        cur.execute(
            """
            INSERT INTO ticket
              (tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data.tour_id,
                seat_id,
                passenger_id,
                data.departure_stop_id,
                data.arrival_stop_id,
            ),
        )
        ticket_id = cur.fetchone()[0]

        # 8) remove those segments from available string
        new_avail = "".join(ch for ch in avail_str if ch not in segments)
        if new_avail == "":
            new_avail = "0"
        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (new_avail, seat_id),
        )

        # 9) decrement each segment in available table
        for i in range(idx_from, idx_to):
            dep = stops[i]
            arr = stops[i + 1]
            cur.execute(
                """
                UPDATE available
                SET seats = seats - 1
                WHERE tour_id = %s
                  AND departure_stop_id = %s
                  AND arrival_stop_id   = %s
                """,
                (data.tour_id, dep, arr),
            )

        conn.commit()
        return {"ticket_id": ticket_id}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/reassign", status_code=204)
def reassign_ticket(data: TicketReassign):
    """
    - If `to_seat` is already occupied → swap the two tickets' seats.
    - Otherwise → move passenger from `from_seat` to `to_seat`.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # (1) find the ticket ID & from_seat_id
        cur.execute(
            """
            SELECT t.id, s.id
            FROM ticket t
            JOIN seat s ON s.id = t.seat_id
            WHERE t.tour_id = %s AND s.seat_num = %s
            """,
            (data.tour_id, data.from_seat),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"No ticket on seat {data.from_seat}")
        from_ticket_id, from_seat_id = row

        # (2) get the to_seat_id
        cur.execute(
            "SELECT id FROM seat WHERE tour_id = %s AND seat_num = %s",
            (data.tour_id, data.to_seat),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"Seat {data.to_seat} not found")
        to_seat_id = row[0]

        # (3) check for an existing ticket on to_seat
        cur.execute(
            "SELECT id FROM ticket WHERE tour_id = %s AND seat_id = %s",
            (data.tour_id, to_seat_id),
        )
        swap = cur.fetchone()
        if swap:
            swap_ticket_id = swap[0]
            # swap their seat_ids
            cur.execute(
                "UPDATE ticket SET seat_id = %s WHERE id = %s",
                (from_seat_id, swap_ticket_id),
            )

        # (4) move the original ticket onto to_seat
        cur.execute(
            "UPDATE ticket SET seat_id = %s WHERE id = %s",
            (to_seat_id, from_ticket_id),
        )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int):
    """
    Delete a ticket and "un-sell" its segments:
     1) restore those segments into seat.available
     2) increment each segment count in available table
     3) delete the ticket (and passenger)
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # find ticket + seat + passenger + stops
        cur.execute(
            """
            SELECT tour_id, seat_id, passenger_id, departure_stop_id, arrival_stop_id
            FROM ticket
            WHERE id = %s
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ticket not found")
        tour_id, seat_id, passenger_id, dep_stop, arr_stop = row

        # look up route_id
        cur.execute("SELECT route_id FROM tour WHERE id = %s", (tour_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(500, "Tour not found")
        route_id = r[0]

        # load ordered stops
        cur.execute(
            "SELECT stop_id FROM routestop WHERE route_id = %s ORDER BY \"order\"",
            (route_id,),
        )
        stops = [r[0] for r in cur.fetchall()]

        idx_from = stops.index(dep_stop)
        idx_to   = stops.index(arr_stop)
        if idx_from >= idx_to:
            raise HTTPException(500, "Invalid ticket stops")

        # segments to restore
        segments = [str(i + 1) for i in range(idx_from, idx_to)]

        # restore into seat.available
        cur.execute("SELECT available FROM seat WHERE id = %s", (seat_id,))
        avail_str = cur.fetchone()[0] or ""
        merged = sorted(set(list(avail_str) + segments), key=lambda x: int(x))
        new_avail = "".join(merged) if merged else "0"
        cur.execute(
            "UPDATE seat SET available = %s WHERE id = %s",
            (new_avail, seat_id),
        )

        # increment each segment back
        for i in range(idx_from, idx_to):
            dep = stops[i]
            arr = stops[i + 1]
            cur.execute(
                """
                UPDATE available
                SET seats = seats + 1
                WHERE tour_id=%s AND departure_stop_id=%s AND arrival_stop_id=%s
                """,
                (tour_id, dep, arr),
            )

        # delete the ticket
        cur.execute("DELETE FROM ticket WHERE id = %s", (ticket_id,))

        # delete the passenger
        cur.execute("DELETE FROM passenger WHERE id = %s", (passenger_id,))

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()
