// src/components/SeatIcon.js
import React from "react";

// Цвета для статусов (можно вынести в constants.js при необходимости)
const COLORS = {
  available: "#a2d5ab",
  blocked:   "#cccccc",
  selected:  "#2196f3",
  occupied:  "#e27c7c"
};

/**
 * SeatIcon — SVG-иконка сиденья автобуса с поддержкой разных статусов.
 *
 * @param {number} seatNum — номер места (число)
 * @param {string} status — "available" | "blocked" | "selected" | "occupied"
 * @param {function} onClick — обработчик клика (опционально)
 */
export default function SeatIcon({ seatNum, status = "available", onClick }) {
  const fill = COLORS[status] || COLORS.available;
  return (
    <div
      style={{
        position: "relative",
        width: 40,
        height: 40,
        display: "inline-block",
        cursor: status === "blocked" ? "default" : "pointer"
      }}
      onClick={status !== "blocked" && onClick ? onClick : undefined}
    >
      <svg
        width="40"
        height="40"
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Сиденье */}
        <rect x="2" y="5" width="28" height="28" rx="8" fill={fill} stroke="#C2C8CA" strokeWidth="2" />
        {/* Спинка */}
        <rect x="26" y="3" width="7" height="28" rx="3.5" fill="#BCC2C5" stroke="#C2C8CA" strokeWidth="1.2" />
        {/* Подголовник */}
        <rect x="30" y="8" width="7" height="13" rx="3.5" fill="#808486" stroke="#C2C8CA" strokeWidth="1.2" />
        {/* Номер */}
        <text
          x="15"
          y="25"
          textAnchor="middle"
          fontSize="17"
          fontFamily="Arial, Helvetica, sans-serif"
          fontWeight="bold"
          fill="#fff"
          opacity="0.9"
        >
          {seatNum}
        </text>
      </svg>
      {/* Иконка пассажира рендерится снаружи */}
    </div>
  );
}

