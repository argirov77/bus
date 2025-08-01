from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..database import get_connection
from ..auth import require_admin_token

router = APIRouter(
    prefix="/report",
    tags=["report"],
    dependencies=[Depends(require_admin_token)],
)

class ReportFilters(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    route_id: Optional[int] = None
    tour_id: Optional[int] = None
    departure_stop_id: Optional[int] = None
    arrival_stop_id: Optional[int] = None

@router.post("/")
def get_report(filters: ReportFilters):
    """
    Генерирует отчёт по проданным билетам с учётом фильтров:
    - Даты (tour.date)
    - Маршрут (route_id)
    - Рейс (tour_id)
    - Остановки (departure_stop_id, arrival_stop_id)
    
    Возвращает:
    - summary: кол-во билетов, сумма продаж
    - tickets: список билетов с price, seat_num, именами остановок и т.д.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        conditions = []
        params = []

        # Фильтр по датам
        if filters.start_date:
            sd = datetime.strptime(filters.start_date, "%Y-%m-%d").date()
            conditions.append("tr.date >= %s")
            params.append(sd)
        if filters.end_date:
            ed = datetime.strptime(filters.end_date, "%Y-%m-%d").date()
            conditions.append("tr.date <= %s")
            params.append(ed)

        # Фильтр по маршруту
        if filters.route_id:
            conditions.append("r.id = %s")
            params.append(filters.route_id)

        # Фильтр по рейсу
        if filters.tour_id:
            conditions.append("t.tour_id = %s")
            params.append(filters.tour_id)

        # Фильтр по остановкам
        if filters.departure_stop_id:
            conditions.append("t.departure_stop_id = %s")
            params.append(filters.departure_stop_id)
        if filters.arrival_stop_id:
            conditions.append("t.arrival_stop_id = %s")
            params.append(filters.arrival_stop_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # СВОДКА: кол-во билетов и сумма продаж
        # JOIN prices pr для вычисления цены
        summary_query = f"""
            SELECT 
                COUNT(*) AS total_tickets,
                COALESCE(SUM(pr.price), 0) AS total_sales
            FROM ticket t
            JOIN tour tr ON t.tour_id = tr.id
            JOIN route r ON tr.route_id = r.id
            JOIN prices pr ON pr.pricelist_id = tr.pricelist_id
                          AND pr.departure_stop_id = t.departure_stop_id
                          AND pr.arrival_stop_id = t.arrival_stop_id
            {where_clause}
        """
        cur.execute(summary_query, tuple(params))
        row = cur.fetchone()
        summary = {
            "total_tickets": row[0],
            "total_sales": float(row[1])
        }

        # ДЕТАЛИ:
        # JOIN seat s для seat_num
        # JOIN stop ds/as_ для имён остановок
        # JOIN prices pr чтобы получить price
        details_query = f"""
            SELECT
                t.id AS ticket_id,
                t.tour_id,
                s.seat_num,
                pr.price,
                p.name AS passenger_name,
                p.phone AS passenger_phone,
                p.email AS passenger_email,
                t.extra_baggage,
                tr.date AS tour_date,
                r.name AS route_name,
                ds.stop_name AS dep_stop_name,
                as_.stop_name AS arr_stop_name
            FROM ticket t
            JOIN tour tr ON t.tour_id = tr.id
            JOIN route r ON tr.route_id = r.id
            JOIN seat s ON t.seat_id = s.id
            LEFT JOIN passenger p ON t.passenger_id = p.id
            LEFT JOIN stop ds ON ds.id = t.departure_stop_id
            LEFT JOIN stop as_ ON as_.id = t.arrival_stop_id
            JOIN prices pr ON pr.pricelist_id = tr.pricelist_id
                           AND pr.departure_stop_id = t.departure_stop_id
                           AND pr.arrival_stop_id = t.arrival_stop_id
            {where_clause}
            ORDER BY tr.date DESC, t.id
        """
        cur.execute(details_query, tuple(params))
        tickets = []
        for row in cur.fetchall():
            tickets.append({
                "ticket_id": row[0],
                "tour_id": row[1],
                "seat_num": row[2],
                "price": float(row[3]),
                "passenger_name": row[4],
                "passenger_phone": row[5],
                "passenger_email": row[6],
                "extra_baggage": bool(row[7]),
                "tour_date": row[8].isoformat(),
                "route_name": row[9],
                "departure_stop_name": row[10],
                "arrival_stop_name": row[11]
            })

        return {"summary": summary, "tickets": tickets}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
