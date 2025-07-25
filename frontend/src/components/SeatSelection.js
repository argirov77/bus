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
    <>
      <div className="seats-grid">
        {seats.map((seat) => {
          const isSelected = seat.seat_num === selectedSeat;
          const statusLabel = seat.available
            ? isSelected
              ? "selected"
              : "available"
            : "occupied";

          return (
            <button
              key={seat.seat_num}
              type="button"
              className={
                "seat " +
                (seat.available ? "available " : "occupied ") +
                (isSelected ? "selected" : "")
              }
              onClick={() => handleClick(seat)}
              disabled={!seat.available}
              aria-pressed={isSelected}
              aria-label={`Seat ${seat.seat_num} ${statusLabel}`}
              title={
                seat.available
                  ? isSelected
                    ? "Ваш выбор"
                    : "Свободное место"
                  : "Место занято"
              }
            >
              {isSelected ? "\u2713" : seat.available ? seat.seat_num : "\u2715"}
            </button>
          );
        })}
      </div>
      <div className="seat-legend">
        <div className="legend-item">
          <span className="legend-box available" aria-hidden="true"></span>
          <span>Свободно</span>
        </div>
        <div className="legend-item">
          <span className="legend-box occupied" aria-hidden="true">\u2715</span>
          <span>Занято</span>
        </div>
        <div className="legend-item">
          <span className="legend-box selected" aria-hidden="true">\u2713</span>
          <span>Выбрано</span>
        </div>
      </div>
    </>
  );
}

export default SeatSelection;
