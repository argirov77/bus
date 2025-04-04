import React from "react";
import "./Seat.css";

export default function Seat({ seat, onSelect, interactive }) {
  // Классы для разных состояний: available, occupied, blocked
  let className = "seat";
  if (seat.status === "available") {
    className += " available";
  } else if (seat.status === "occupied") {
    className += " occupied";
  } else if (seat.status === "blocked") {
    className += " blocked";
  }

  return (
    <button
      className={className}
      onClick={() => interactive && seat.status === "available" && onSelect(seat)}
      disabled={seat.status !== "available"}
    >
      {seat.seat_num}
    </button>
  );
}
