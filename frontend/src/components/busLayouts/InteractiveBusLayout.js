import React, { useState } from "react";
import "./InteractiveBusLayout.css";

// Пример данных раскладки для автобуса (это можно вынести в JSON-файл)
const layoutData = [
  // Первый ряд: водительские места
  { type: "driver", row: 1, col: 1 },
  { type: "driver", row: 1, col: 2 },
  // Второй ряд: сиденья
  { type: "seat", seatNum: 1, row: 2, col: 1 },
  { type: "seat", seatNum: 2, row: 2, col: 2 },
  { type: "seat", seatNum: 3, row: 2, col: 3 },
  { type: "seat", seatNum: 4, row: 2, col: 4 },
  // Третий ряд: проход и сиденья
  { type: "door", row: 3, col: 1 },
  { type: "seat", seatNum: 5, row: 3, col: 2 },
  { type: "seat", seatNum: 6, row: 3, col: 3 },
  { type: "seat", seatNum: 7, row: 3, col: 4 },
  // Четвертый ряд: сиденья
  { type: "seat", seatNum: 8, row: 4, col: 1 },
  { type: "seat", seatNum: 9, row: 4, col: 2 },
  { type: "seat", seatNum: 10, row: 4, col: 3 },
  { type: "seat", seatNum: 11, row: 4, col: 4 },
  // Добавьте остальные ряды по необходимости…
];

const defaultSeatStatus = {}; // например, {1: "vacant", 2: "occupied", ...}

export default function InteractiveBusLayout({ onSeatSelect, editMode }) {
  // Храним статус мест: "vacant", "occupied", "selected", "closed"
  const [seatStatus, setSeatStatus] = useState(defaultSeatStatus);

  // Пример: функция обработки клика по месту
  const handleClick = (item) => {
    if (item.type !== "seat") return; // только для мест
    const currentStatus = seatStatus[item.seatNum] || "vacant";

    // Если место закрыто, ничего не делаем
    if (currentStatus === "closed") return;

    // Если место занято и не в режиме редактирования, можно запустить tooltip (не реализовано здесь)
    if (currentStatus === "occupied" && !editMode) {
      // Например, показать всплывающее окно с именем пассажира
      return;
    }

    // В режиме редактирования или если место свободно, переключаем выбор
    let newStatus;
    if (currentStatus === "vacant") {
      newStatus = "selected";
    } else if (currentStatus === "selected") {
      newStatus = "vacant";
    } else {
      newStatus = currentStatus;
    }
    setSeatStatus({ ...seatStatus, [item.seatNum]: newStatus });
    if (onSeatSelect) onSeatSelect(item.seatNum, newStatus);
  };

  return (
    <div className="bus-layout-container">
      {layoutData.map((item, index) => {
        const style = {
          gridRow: item.row,
          gridColumn: item.col,
        };
        let content = "";
        let className = "bus-item";
        if (item.type === "seat") {
          const status = seatStatus[item.seatNum] || "vacant";
          className += ` seat ${status}`;
          content = item.seatNum;
        } else if (item.type === "door") {
          className += " door";
          content = "🚪";
        } else if (item.type === "driver") {
          className += " driver";
          content = "🚗";
        }
        return (
          <div
            key={index}
            className={className}
            style={style}
            onClick={() => handleClick(item)}
          >
            {content}
          </div>
        );
      })}
    </div>
  );
}
