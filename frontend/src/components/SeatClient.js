// src/components/SeatClient.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import BusLayoutNeoplan from "./busLayouts/BusLayoutNeoplan";
import BusLayoutTravego  from "./busLayouts/BusLayoutTravego";

const API = "http://127.0.0.1:8000";

// Цвета для клиента
const CLIENT_COLORS = {
  blocked:   "#ddd",    // недоступное
  available: "#4caf50", // зелёное
  selected:  "#2196f3"  // синим помеченное выбранное
};

/**
 * SeatClient — для страницы покупки билета.
 *
 * Props:
 *  - tourId
 *  - departureStopId
 *  - arrivalStopId
 *  - layoutVariant (1 или 2)
 *  - onSelect(seatNum) — коллбэк при выборе места
 */
export default function SeatClient({
  tourId,
  departureStopId,
  arrivalStopId,
  layoutVariant,
  onSelect
}) {
  const [seats, setSeats]             = useState([]); // [{seat_num, status}, ...]
  const [selectedSeat, setSelectedSeat] = useState(null);

  // Загружаем статусы мест
  useEffect(() => {
    if (!tourId || !departureStopId || !arrivalStopId) {
      setSeats([]);
      setSelectedSeat(null);
      return;
    }
    axios.get(`${API}/seat`, {
      params: {
        tour_id:           tourId,
        departure_stop_id: departureStopId,
        arrival_stop_id:   arrivalStopId
      }
    })
    .then(res => {
      // оставляем только "available" / "blocked"
      const arr = res.data.seats.map(s => ({
        seat_num: s.seat_num,
        status:   s.status === "available" ? "available" : "blocked"
      }));
      setSeats(arr);
      setSelectedSeat(null);
    })
    .catch(console.error);
  }, [tourId, departureStopId, arrivalStopId]);

  // Логика клика по месту
  const handleSelect = (num) => {
    const seat = seats.find(s => s.seat_num === num);
    if (!seat || seat.status !== "available") return;
    setSelectedSeat(num);
    onSelect && onSelect(num);
  };

  // renderCell для скелетного режима
  const renderCell = (seatNum) => {
    const seat = seats.find(s => s.seat_num === seatNum);
    const status = seat ? seat.status : "blocked";
    let bg;
    if (status === "blocked") {
      bg = CLIENT_COLORS.blocked;
    } else if (seatNum === selectedSeat) {
      bg = CLIENT_COLORS.selected;
    } else {
      bg = CLIENT_COLORS.available;
    }

    return (
      <button
        key={seatNum}
        type="button"
        onClick={() => handleSelect(seatNum)}
        style={{
          width: 40,
          height: 40,
          margin: 0,
          backgroundColor: bg,
          border: "1px solid #888",
          borderRadius: 4,
          cursor: status === "available" ? "pointer" : "default"
        }}
      >
        {seatNum}
      </button>
    );
  };

  const Layout = layoutVariant === 1
    ? BusLayoutNeoplan
    : BusLayoutTravego;

  // Рендерим только skeleton-режим с renderCell
  return <Layout renderCell={renderCell} />;
}
