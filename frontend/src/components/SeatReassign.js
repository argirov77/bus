// src/components/SeatReassign.js
import React, { useState, useRef } from "react";
import BusLayoutNeoplan from "./busLayouts/BusLayoutNeoplan";
import BusLayoutTravego  from "./busLayouts/BusLayoutTravego";

/**
 * SeatReassign
 * — initialSeats: [{ seat_id, seat_num, status, passenger?, ticket? }, …]
 * — onSwap(fromSeatNum, toSeatNum)
 * — onReassign(fromSeatNum, toSeatNum)
 * — onDelete(seatNum)
 */
export default function SeatReassign({
  layoutVariant,
  initialSeats,
  onSwap,
  onReassign,
  onDelete
}) {
  const [seats, setSeats] = useState(initialSeats);
  const dragFrom = useRef(null);

  // при старте переноса запомним номер
  const handleDragStart = seatNum => e => {
    dragFrom.current = seatNum;
    e.dataTransfer.effectAllowed = "move";
  };

  // разрешаем дроп
  const handleDragOver = e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  // когда бросили на другое кресло
  const handleDrop = seatNum => e => {
    e.preventDefault();
    const from = dragFrom.current;
    const to   = seatNum;
    dragFrom.current = null;

    if (from === to) return;

    const fromSeat = seats.find(s => s.seat_num === from);
    const toSeat   = seats.find(s => s.seat_num === to);

    // если оба occupied — просто swap
    if (fromSeat.status === "occupied" && toSeat.status === "occupied") {
      onSwap(from, to);
    }
    // occupied → available/blocked — reassign
    else if (fromSeat.status === "occupied" && toSeat.status !== "occupied") {
      onReassign(from, to);
    }
  };

  // если бросили мимо — удаляем билет
  const handleContainerDrop = e => {
    e.preventDefault();
    const from = dragFrom.current;
    dragFrom.current = null;
    // только если occupied
    if (seats.find(s => s.seat_num === from)?.status === "occupied") {
      onDelete(from);
    }
  };

  // строим пропсы для схемы
  const layoutProps = {
    seats: seats.map(s => ({
      seat_num: s.seat_num,
      status:   s.status
    })),
    renderCell: (seatNum, status) => (
      <button
        draggable={status === "occupied"}
        onDragStart={handleDragStart(seatNum)}
        onDragOver={handleDragOver}
        onDrop={handleDrop(seatNum)}
        style={{
          width: 40,
          height: 40,
          marginRight: 4,
          backgroundColor:
            status === "occupied" ? "#e27c7c" :
            status === "blocked"  ? "#cccccc" :
                                    "#a2d5ab",
          cursor: status === "occupied" ? "grab" : "default",
          border: "1px solid #888",
          borderRadius: 4
        }}
      >
        {seatNum}
      </button>
    )
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDrop={handleContainerDrop}
      style={{ display: "inline-block" }}
    >
      {layoutVariant === 1
        ? <BusLayoutNeoplan {...layoutProps} />
        : <BusLayoutTravego  {...layoutProps} />
      }
    </div>
  );
}
