import React from "react";
import doorIcon from "../../assets/icons/door.svg";
import wcIcon from "../../assets/icons/wc.svg";

// Layout with door and WC placeholders; null represents passage
const layoutHorizontal = [
  [1, 2, null, 3, 4],
  [5, 6, null, 7, 8],
  [9, 10, null, 11, 12],
  [13, 14, null, 15, 16],
  [17, 18, null, 19, 20],
  [21, 22, null, 23, 24],
  [25, 26, null, "door", "wc"],
  [29, 30, null, 31, 32],
  [33, 34, null, 35, 36],
  [37, 38, null, 39, 40],
  [41, 42, null, 43, 44],
  [45, 46, null, 47, 48],
];

export default function BusLayoutHorizontal(props) {
  const {
    renderCell,
    seats = [],
    selectedSeats = [],
    toggleSeat,
    interactive = false,
  } = props;

  // Skeleton mode
  if (typeof renderCell === "function") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {layoutHorizontal.map((row, i) => (
          <div key={i} style={{ display: "flex", gap: 4 }}>
            {row.map((item, j) => {
              if (item === null) return <div key={j} style={{ width: 40 }} />;
              if (item === "door")
                return (
                  <img key={j} src={doorIcon} alt="Door" style={{ width: 40, height: 40 }} />
                );
              if (item === "wc")
                return (
                  <img key={j} src={wcIcon} alt="WC" style={{ width: 40, height: 40 }} />
                );
              return <React.Fragment key={j}>{renderCell(item)}</React.Fragment>;
            })}
          </div>
        ))}
      </div>
    );
  }

  // Legacy interactive mode
  const isCreation = seats.length === 0;
  const statusMap = {};
  if (!isCreation) {
    seats.forEach((s) => {
      statusMap[s.seat_num] = s.status;
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {layoutHorizontal.map((row, i) => (
        <div key={i} style={{ display: "flex", gap: 4 }}>
          {row.map((item, j) => {
            if (item === null) return <div key={j} style={{ width: 40 }} />;
            if (item === "door")
              return (
                <img key={j} src={doorIcon} alt="Door" style={{ width: 40, height: 40 }} />
              );
            if (item === "wc")
              return <img key={j} src={wcIcon} alt="WC" style={{ width: 40, height: 40 }} />;

            const seatNum = item;
            let bg;
            let isOcc = false;
            if (isCreation) {
              bg = selectedSeats.includes(seatNum) ? "#4caf50" : "#ddd";
            } else {
              const st = statusMap[seatNum] || "available";
              if (st === "available") bg = "#a2d5ab";
              else if (st === "occupied") {
                bg = "#e27c7c";
                isOcc = true;
              } else bg = "#cccccc";
            }

            return (
              <button
                key={j}
                type="button"
                onClick={() => interactive && toggleSeat && toggleSeat(seatNum)}
                style={{
                  width: 40,
                  height: 40,
                  backgroundColor: bg,
                  border: "1px solid #888",
                  borderRadius: 4,
                  cursor: interactive ? "pointer" : "default",
                  opacity: isOcc ? 0.6 : 1,
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
