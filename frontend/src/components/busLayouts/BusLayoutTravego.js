import React from "react";

// Пример схемы Travego (по 4 элемента в ряду). 
// Дополните нужным количеством рядов.
const layoutTravego = [
  [1, 2, 3, 4],
  [5, 6, 7, 8],
  [9, 10, 11, 12],
  [13, 14, 15, 16],
  [17, 18, 19, 20],
  [21, 22, 23, 24],
  [25, 26, 27, 28],
  [29, 30, 31, 32],
  [33, 34, 35, 36],
  [37, 38, 39, 40],
  [41, 42, 43, 44],
  [45, 46, 47, 48],
];

function BusLayoutTravego({
  selectedSeats = [],
  seats = [],
  toggleSeat,
  interactive = false
}) {
  const handleClick = (seatNum) => {
    if (!interactive) return;
    if (toggleSeat) {
      toggleSeat(seatNum);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {layoutTravego.map((row, rowIndex) => (
        <div key={rowIndex} style={{ display: "flex", marginBottom: "4px" }}>
          {row.map((seatNum, seatIndex) => {
            const isSelected = selectedSeats.includes(seatNum);
            return (
              <button
                key={seatIndex}
                onClick={() => handleClick(seatNum)}
                style={{
                  width: "40px",
                  height: "40px",
                  marginRight: "4px",
                  backgroundColor: isSelected ? "green" : "#ccc",
                  cursor: interactive ? "pointer" : "default",
                }}
              >
                {seatNum}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default BusLayoutTravego;
