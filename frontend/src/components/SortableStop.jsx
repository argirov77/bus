import React from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

export function SortableStop({
  id,
  routeStop,
  getStopName,
  extractTime,
  onDeleteStop,
  onUpdateTime
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    border: "1px solid #ccc",
    padding: "8px",
    marginBottom: "8px",
    backgroundColor: "#fff",
    cursor: "grab"
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <div>
        <strong>{getStopName(routeStop.stop_id)}</strong> (ID: {routeStop.id})
      </div>
      <div>Порядок: {routeStop.order}</div>
      <div style={{ marginTop: "8px" }}>
        Время прибытия:{" "}
        <input
          type="time"
          value={extractTime(routeStop.arrival_time)}
          onChange={e => onUpdateTime(routeStop.id, "arrival_time", e.target.value)}
        />
      </div>
      <div>
        Время отправления:{" "}
        <input
          type="time"
          value={extractTime(routeStop.departure_time)}
          onChange={e => onUpdateTime(routeStop.id, "departure_time", e.target.value)}
        />
      </div>
      <div style={{ marginTop: "8px" }}>
        <button onClick={() => onDeleteStop(routeStop.id)}>Удалить</button>
      </div>
    </div>
  );
}
