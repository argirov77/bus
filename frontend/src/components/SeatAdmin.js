// src/components/SeatAdmin.js

import React, { useState, useEffect } from "react";
import axios from "axios";
import Button from "@mui/material/Button";
import styles from "./SeatAdmin.module.css";

import BusLayoutNeoplan from "./busLayouts/BusLayoutNeoplan";
import BusLayoutTravego  from "./busLayouts/BusLayoutTravego";
import BusLayoutHorizontal from "./busLayouts/BusLayoutHorizontal";

import {
  DndContext,
  useSensor,
  useSensors,
  PointerSensor,
  useDraggable,
  useDroppable
} from "@dnd-kit/core";

import { API } from "../config";

export default function SeatAdmin({
  tourId,
  layoutVariant,
  seatEdits,
  onToggle,      // клики для блокировки/разблокировки
  onReassign,    // (fromSeatNum, toSeatNum) — пересадка
  onRemove       // (seatNum) — удаление (перетянуто в пустоту)
}) {
  const [initialSeats, setInitialSeats] = useState([]);

  // 1) загрузка статусов
  useEffect(() => {
    axios.get(`${API}/seat`, { params: { tour_id: tourId, adminMode: 1 } })
      .then(r => setInitialSeats(r.data.seats))
      .catch(console.error);
  }, [tourId]);

  // сенсоры dnd-kit
  const sensors = useSensors(useSensor(PointerSensor));

  // 2) обработчик конца перетаскивания
  const handleDragEnd = ({ active, over }) => {
    const from = Number(active.id);
    const to   = over ? Number(over.id) : null;

    if (to === null) {
      // отпустили в пустоту — удаляем билет
      onRemove && onRemove(from);
    } else if (to !== from) {
      // пересадка или обмен
      onReassign && onReassign(from, to);
    }
  };

  // 3) renderCell для BusLayout
  const renderCell = seatNum => {
    // получаем исходный статус
    const orig = initialSeats.find(s => s.seat_num === seatNum);
    const origStatus = orig?.status || "available";

    // применяем локальную правку
    const status = seatEdits.hasOwnProperty(seatNum)
      ? (seatEdits[seatNum] ? "blocked" : "available")
      : origStatus;

    const isOccupied = status === "occupied";

    // dnd-kit draggable & droppable
    const { setNodeRef: dragRef, listeners, attributes, transform, isDragging } =
      useDraggable({ id: String(seatNum), disabled: status !== "occupied" });

    const { setNodeRef: dropRef, isOver } =
      useDroppable({ id: String(seatNum) });

    const style = {
      transform: transform
        ? `translate3d(${transform.x}px, ${transform.y}px, 0)`
        : undefined,
      zIndex: isDragging ? 10 : 1,
      opacity: isOccupied ? 0.6 : 1
    };

    return (
      <div key={seatNum} ref={dropRef} className={styles.seatContainer}>
        <Button
          ref={dragRef}
          {...listeners}
          {...attributes}
          onClick={() => onToggle && onToggle(seatNum)}
          className={`${styles.seatButton} ${styles[status]} ${isOver ? styles.over : ""}`}
          style={style}
        >
          {seatNum}
        </Button>
      </div>
    );
  };

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      {layoutVariant === 1 ? (
        <BusLayoutNeoplan renderCell={renderCell} />
      ) : layoutVariant === 2 ? (
        <BusLayoutTravego renderCell={renderCell} />
      ) : (
        <BusLayoutHorizontal renderCell={renderCell} />
      )}
    </DndContext>
  );
}
