import React from "react";
import "./BusLayout.css";

// Пример матрицы для автобуса Neoplan (46 мест)
// Каждая строка – это ряд мест, где null обозначает отсутствие места (например, проход)
const layout = [
  [1, 2, null, 3, 4],
  [5, 6, null, 7, 8],
  [9, 10, null, 11, 12],
  [13, 14, null, 15, 16],
  [17, 18, null, 19, 20],
  [21, 22, null, 23, 24],
  [25, 26, null, 27, 28],
  [29, 30, null, 31, 32],
  [33, 34, null, 35, 36],
  [37, 38, null, 39, 40],
  [41, 42, null, 43, 44],
  [45, 46, null, null, null]
];

const BusLayoutNeoplan = ({ selectedSeats, toggleSeat }) => {
  return (
    <div className="bus-layout">
      <h4>Neoplan Layout (46 мест)</h4>
      {layout.map((row, rowIndex) => (
        <div key={rowIndex} className="bus-row">
          {row.map((seat, colIndex) => {
            if (seat === null) {
              return <div key={colIndex} className="bus-empty"></div>;
            }
            const isSelected = selectedSeats.includes(seat);
            return (
              <div
                key={colIndex}
                className={`bus-seat ${isSelected ? "selected" : "available"}`}
                onClick={() => toggleSeat(seat)}
              >
                {seat}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
};

export default BusLayoutNeoplan;
