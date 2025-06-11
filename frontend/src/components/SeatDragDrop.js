// src/components/SeatDragDrop.js
import React, { useState } from "react";
import { DndProvider, useDrag, useDrop } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";
import axios from "axios";
import BusLayoutNeoplan from "./busLayouts/BusLayoutNeoplan";
import BusLayoutTravego  from "./busLayouts/BusLayoutTravego";

import { API } from "../config";

const ITEM_TYPE = "SEAT";

function SeatCell({ seat, layoutVariant, onInfo, onDropSeat }) {
  const [{ isDragging }, drag] = useDrag({
    type: ITEM_TYPE,
    item: { ticket_id: seat.ticket_id, from: seat.seat_num },
    canDrag: () => seat.status === "occupied"
  });
  const [, drop] = useDrop({
    accept: ITEM_TYPE,
    drop: (item) => onDropSeat(item, seat.seat_num),
    canDrop: (item) => item.from !== seat.seat_num
  });

  return (
    <div ref={ref => drag(drop(ref))} style={{ opacity: isDragging ? 0.5 : 1 }}>
      <button
        onClick={() => seat.status==="occupied" && onInfo(seat)}
        style={{
          width: 40, height: 40, margin: 4,
          backgroundColor: {
            available: "#a2d5ab",
            occupied:  "#e27c7c",
            blocked:   "#cccccc"
          }[seat.status],
          cursor: seat.status==="occupied" ? "grab" : "default"
        }}
      >
        {seat.seat_num}
      </button>
    </div>
  );
}

export default function SeatDragDrop({
  tourId, layoutVariant, departureStopId, arrivalStopId
}) {
  const [seats, setSeats] = useState([]);
  const [modal, setModal] = useState(null);

  React.useEffect(() => {
    axios.get(`${API}/seat`, {
      params: { tour_id: tourId, adminMode: true }
    }).then(r => setSeats(r.data.seats))
     .catch(console.error);
  }, [tourId]);

  const reload = () => {
    axios.get(`${API}/seat`, {
      params: { tour_id: tourId, adminMode: true }
    }).then(r => setSeats(r.data.seats))
     .catch(console.error);
  };

  const handleInfo = (seat) => {
    setModal(seat);
  };

  const handleDrop = async (item, toSeatNum) => {
    const fromTicket = item.ticket_id;
    const toSeat = seats.find(s=>s.seat_num===toSeatNum);
    if (!toSeat) return;
    if (toSeat.status === "occupied") {
      // swap
      await axios.post(`${API}/tickets/${fromTicket}/swap`, {
        other_ticket_id: toSeat.ticket_id
      });
    } else {
      // move
      await axios.post(`${API}/tickets/${fromTicket}/move`, {
        new_seat_num: toSeatNum
      });
    }
    reload();
  };

  const handleDelete = async (item) => {
    // drop вне зоны, удаляем
    await axios.delete(`${API}/tickets/${item.ticket_id}`);
    reload();
  };

  return (
    <DndProvider backend={HTML5Backend}>
      <div style={{ userSelect: "none" }}>
        {layoutVariant===1
          ? <BusLayoutNeoplan seats={seats} CellRenderer={SeatCell} />
          : <BusLayoutTravego seats={seats}  CellRenderer={SeatCell} />
        }
      </div>
      {modal && (
        <div className="modal">
          <h3>Пассажир #{modal.ticket_id}</h3>
          <p>Имя: {modal.passenger.name}</p>
          <p>Телефон: {modal.passenger.phone}</p>
          <p>Email: {modal.passenger.email}</p>
          <button onClick={()=>setModal(null)}>Закрыть</button>
        </div>
      )}
    </DndProvider>
  );
}
