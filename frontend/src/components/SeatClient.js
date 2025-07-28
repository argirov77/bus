// src/components/SeatClient.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import BusLayoutNeoplan from "./busLayouts/BusLayoutNeoplan";
import BusLayoutTravego from "./busLayouts/BusLayoutTravego";
import SeatIcon from "./SeatIcon";

import { API } from "../config";
import { CLIENT_COLORS } from "../constants";

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
  const [seats, setSeats] = useState([]); // [{seat_num, status}, ...]
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
    let status = seat ? seat.status : "blocked";
    if (seatNum === selectedSeat) {
      status = "selected";
    }

    return (
      <SeatIcon
        key={seatNum}
        seatNum={seatNum}
        status={status}
        onClick={() => handleSelect(seatNum)}
      />
    );
  };

  const Layout = layoutVariant === 1
    ? BusLayoutNeoplan
    : BusLayoutTravego;

  // Рендерим только skeleton-режим с renderCell
  return <Layout renderCell={renderCell} />;
}

