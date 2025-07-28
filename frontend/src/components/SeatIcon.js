// src/components/SeatIcon.js
import React from "react";
import passImg from "../assets/icons/pass.svg";

const COLORS = {
  available: "#a2d5ab",
  blocked:   "#cccccc",
  selected:  "#2196f3",
  occupied:  "#e27c7c"
};

export default function SeatIcon({ number, status = "available" }) {
  const fill = COLORS[status] || COLORS.available;
  return (
    <div style={{ position: "relative", width: 40, height: 40 }}>
      <svg
        width="40"
        height="40"
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect x="2" y="5" width="28" height="28" rx="8" fill={fill} stroke="#C2C8CA" strokeWidth="2" />
        <rect x="26" y="3" width="7" height="28" rx="3.5" fill="#BCC2C5" stroke="#C2C8CA" strokeWidth="1.2" />
        <rect x="30" y="8" width="7" height="13" rx="3.5" fill="#808486ff" stroke="#C2C8CA" strokeWidth="1.2" />
        <text x="15" y="25" textAnchor="middle" fontSize="17" fontFamily="Arial, Helvetica, sans-serif" fontWeight="bold" fill="#fff" opacity="0.9">
          {number}
        </text>
      </svg>
      {status === "occupied" && (
        <img src={passImg} alt="passenger" style={{ position: "absolute", top: 0, left: 0, width: 40, height: 40 }} />
      )}
    </div>
  );
}
