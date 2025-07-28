import React from "react";
import { CLIENT_COLORS } from "../constants";

export default function SeatIcon({ seatNum, status, onClick }) {
  const bg = CLIENT_COLORS[status] || CLIENT_COLORS.available;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: 40,
        height: 40,
        margin: 0,
        backgroundColor: bg,
        border: "1px solid #888",
        borderRadius: 4,
        cursor: status === "blocked" ? "default" : "pointer"
      }}
    >
      {seatNum}
    </button>
  );
}
