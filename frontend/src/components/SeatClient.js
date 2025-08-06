// src/components/SeatClient.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import BusLayoutNeoplan from "./busLayouts/BusLayoutNeoplan";
import BusLayoutTravego from "./busLayouts/BusLayoutTravego";
import BusLayoutHorizontal from "./busLayouts/BusLayoutHorizontal";
import SeatIcon from "./SeatIcon";

import { API } from "../config";

/**
 * SeatClient — для страницы покупки билета.
 *
 * Props:
 *  - tourId
 *  - departureStopId
 *  - arrivalStopId
 *  - layoutVariant (1, 2 или 3)
 *  - selectedSeats      — массив выбранных мест
 *  - maxSeats           — максимально допустимое кол-во мест
 *  - onChange(seats[])  — коллбэк при выборе мест
 */
export default function SeatClient({
  tourId,
  departureStopId,
  arrivalStopId,
  layoutVariant,
  selectedSeats = [],
  maxSeats = 1,
  onChange
}) {
  const [seats, setSeats] = useState([]); // [{seat_num, status}, ...]

  // Загружаем статусы мест
  useEffect(() => {
    if (!tourId || !departureStopId || !arrivalStopId) {
      setSeats([]);
      onChange && onChange([]);
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
      onChange && onChange([]);
    })
    .catch(console.error);
  }, [tourId, departureStopId, arrivalStopId, onChange]);

  // Логика клика по месту
  const handleSelect = (num) => {
    const seat = seats.find(s => s.seat_num === num);
    if (!seat || seat.status !== "available") return;
    let newSelection;
    if (selectedSeats.includes(num)) {
      newSelection = selectedSeats.filter(s => s !== num);
    } else {
      if (selectedSeats.length >= maxSeats) return;
      newSelection = [...selectedSeats, num];
    }
    onChange && onChange(newSelection);
  };

  // renderCell для скелетного режима
  const renderCell = (seatNum) => {
    const seat = seats.find(s => s.seat_num === seatNum);
    let status = seat ? seat.status : "blocked";
    if (selectedSeats.includes(seatNum)) {
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

  // Подбор раскладки по варианту
  let Layout;
  if (layoutVariant === 1) Layout = BusLayoutNeoplan;
  else if (layoutVariant === 2) Layout = BusLayoutTravego;
  else Layout = BusLayoutHorizontal;

  // Рендерим skeleton-режим с renderCell
  return <Layout renderCell={renderCell} />;
}
