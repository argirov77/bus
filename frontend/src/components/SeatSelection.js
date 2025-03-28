import React, { useState } from "react";
import "./SeatSelection.css";

function SeatSelection({ seats = [], onSelect }) {
  const [selectedSeat, setSelectedSeat] = useState(null);

  const handleClick = (seat) => {
    if (!seat.available) return;
    setSelectedSeat(seat.seat_num);
    if (onSelect) {
      onSelect(seat);
    }
  };

  return (
    <div className="seats-grid">
      {seats.map((seat) => (
        <div
          key={seat.seat_num}
          className={
            "seat " +
            (seat.available ? "available " : "occupied ") +
            (seat.seat_num === selectedSeat ? "selected" : "")
          }
          onClick={() => handleClick(seat)}
        >
          {seat.seat_num}
        </div>
      ))}
    </div>
  );
}

export default SeatSelection;
