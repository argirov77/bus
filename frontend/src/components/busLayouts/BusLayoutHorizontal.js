import React from "react";
import doorIcon from "../../assets/icons/door.svg";
import wheelIcon from "../../assets/icons/wheel.svg";
import wcIcon from "../../assets/icons/wc.svg";

// Генерируем две длинные горизонтальные линии с иконками
const topRow = ["door", ...Array.from({ length: 24 }, (_, i) => i + 1), "wc"];
const bottomRow = ["wheel", ...Array.from({ length: 25 }, (_, i) => i + 25)];
const layout = [topRow, bottomRow];

/**
 * BusLayoutHorizontal — горизонтальная раскладка автобуса
 * @param {function} renderCell — функция для отрисовки сиденья по номеру
 */
export default function BusLayoutHorizontal({ renderCell }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {layout.map((row, rowIdx) => (
        <div key={rowIdx} style={{ display: "flex", flexDirection: "row", gap: 4 }}>
          {row.map((cell, cellIdx) => {
            if (cell === "door") {
              return (
                <img
                  key={cellIdx}
                  src={doorIcon}
                  alt="Door"
                  style={{ width: 40, height: 40 }}
                />
              );
            }
            if (cell === "wheel") {
              return (
                <img
                  key={cellIdx}
                  src={wheelIcon}
                  alt="Steering wheel"
                  style={{ width: 40, height: 40 }}
                />
              );
            }
            if (cell === "wc") {
              return (
                <img
                  key={cellIdx}
                  src={wcIcon}
                  alt="WC"
                  style={{ width: 40, height: 40 }}
                />
              );
            }
            return (
              <React.Fragment key={cellIdx}>
                {typeof renderCell === "function" ? renderCell(cell) : cell}
              </React.Fragment>
            );
          })}
        </div>
      ))}
    </div>
  );
}

