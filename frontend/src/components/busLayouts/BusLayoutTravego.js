// src/components/busLayouts/BusLayoutTravego.js

import React from "react";

// Схема Travego — пример
const layoutTravego = [
  [1, 2, null, 3, 4],
  [5, 6, null, 7, 8],
  [9, 10, null, 11, 12],
  [13, 14, null, 15, 16],
  [17, 18, null, 19, 20],
  [21, 22, null, 23, 24],
  [25, 26, null, null, null],
  [29, 30, null, 31, 32],
  [33, 34, null, 35, 36],
  [37, 38, null, 39, 40],
  [41, 42, null, 43, 44],
  [45, 46, null, 47, 48],
  // … ваша конкретная схема …
];

/**
 * Только отрисовывает расположение Travego, 
 * вызывает `renderCell(seatNum)` для каждой кнопки.
 */
export default function BusLayoutTravego({ renderCell }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {layoutTravego.map((row, rowIdx) => (
        <div key={rowIdx} style={{ display: "flex", flexDirection: "row", gap: 4 }}>
          {row.map((seatNum, cellIdx) => {
            if (seatNum === null) {
              return <div key={cellIdx} style={{ width: 40 }} />;
            }
            return (
              <React.Fragment key={cellIdx}>
                {renderCell(seatNum)}
              </React.Fragment>
            );
          })}
        </div>
      ))}
    </div>
  );
}
