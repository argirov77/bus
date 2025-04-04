import React from "react";

// Пример схемы Neoplan (по 5 элементов в ряду, где null — проход)
const layoutNeoplan = [
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
  [45, 46, null, null,null,],
];

function BusLayoutNeoplan({
  selectedSeats = [], // массив номеров сидений, которые считаем "выбранными"
  seats = [],         // здесь можно было бы получить статусы мест (если нужно)
  toggleSeat,         // функция (seatNum) => void
  interactive = false // флаг, можно ли кликать по местам
}) {
  // Обработчик клика по месту
  const handleClick = (seatNum) => {
    if (!interactive) return; // Если не интерактивно, игнорируем клики
    if (toggleSeat) {
      toggleSeat(seatNum);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {layoutNeoplan.map((row, rowIndex) => (
        <div key={rowIndex} style={{ display: "flex", marginBottom: "4px" }}>
          {row.map((seatNum, seatIndex) => {
            if (seatNum === null) {
              // Это проход
              return <div key={seatIndex} style={{ width: "20px" }} />;
            }
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

export default BusLayoutNeoplan;
