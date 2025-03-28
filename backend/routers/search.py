from fastapi import APIRouter, Query, HTTPException
from database import get_connection
from datetime import datetime

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/departures")
def get_departures():
    """
    Возвращает список уникальных остановок отправления, где есть цены
    и/или доступные места (из таблицы available, где seats > 0).
    """
    conn = get_connection()
    cur = conn.cursor()

    # Остановка отправления из таблицы Prices
    cur.execute("SELECT DISTINCT departure_stop_id FROM prices")
    price_departures = {row[0] for row in cur.fetchall()}

    # Остановка отправления из таблицы Available (с наличием мест)
    cur.execute("SELECT DISTINCT departure_stop_id FROM available WHERE seats > 0")
    available_departures = {row[0] for row in cur.fetchall()}

    all_departures = list(price_departures.union(available_departures))
    stops_list = []
    if all_departures:
        cur.execute("SELECT id, stop_name FROM stop WHERE id = ANY(%s)", (all_departures,))
        stops_list = [{"id": row[0], "stop_name": row[1]} for row in cur.fetchall()]

    cur.close()
    conn.close()
    return stops_list

@router.get("/arrivals")
def get_arrivals(departure_stop_id: int = Query(..., description="ID остановки отправления")):
    """
    Возвращает список остановок прибытия для заданной отправной остановки,
    где для указанного departure_stop_id существует запись в таблице Prices и
    доступные места (из таблицы Available, seats > 0).
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Получаем arrival_stop_id из Prices для заданной остановки отправления
    cur.execute("""
        SELECT DISTINCT arrival_stop_id
        FROM prices
        WHERE departure_stop_id = %s
    """, (departure_stop_id,))
    price_arrivals = {row[0] for row in cur.fetchall()}
    
    # Получаем arrival_stop_id из Available с доступными местами
    cur.execute("""
        SELECT DISTINCT arrival_stop_id
        FROM available
        WHERE departure_stop_id = %s AND seats > 0
    """, (departure_stop_id,))
    available_arrivals = {row[0] for row in cur.fetchall()}
    
    # Требуем, чтобы остановка была и в ценах, и в доступных местах
    arrivals = list(price_arrivals.intersection(available_arrivals))
    
    stops_list = []
    if arrivals:
        cur.execute("SELECT id, stop_name FROM stop WHERE id = ANY(%s)", (arrivals,))
        stops_list = [{"id": row[0], "stop_name": row[1]} for row in cur.fetchall()]

    cur.close()
    conn.close()
    return stops_list

@router.get("/dates")
def get_dates(departure_stop_id: int, arrival_stop_id: int):
    """
    Возвращает список доступных дат (рейсов) для сегмента между заданными остановками,
    основываясь на таблице Tour и наличии свободных мест (Available).
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT DISTINCT t.date
        FROM tour t
        JOIN available a ON a.tour_id = t.id
        WHERE a.departure_stop_id = %s 
          AND a.arrival_stop_id = %s 
          AND a.seats > 0
        ORDER BY t.date;
    """, (departure_stop_id, arrival_stop_id))
    
    dates = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return dates

