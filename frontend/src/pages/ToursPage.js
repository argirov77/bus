// src/pages/ToursPage.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import BusLayoutNeoplan from "../components/busLayouts/BusLayoutNeoplan";
import BusLayoutTravego  from "../components/busLayouts/BusLayoutTravego";
import SeatAdmin         from "../components/SeatAdmin";

import editIcon   from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import saveIcon   from "../assets/icons/save.png";
import cancelIcon from "../assets/icons/cancel.png";

const API = "http://127.0.0.1:8000";

export default function ToursPage() {
  // — reference data —
  const [tours, setTours]           = useState([]);
  const [routes, setRoutes]         = useState([]);
  const [pricelists, setPricelists] = useState([]);
  const [stops, setStops]           = useState([]);
  const stopsMap = Object.fromEntries(stops.map(s => [s.id, s.stop_name]));

  // — new‐tour form state —
  const [newTour, setNewTour] = useState({
    route_id: "", pricelist_id: "", date: "", layout_variant: "", activeSeats: []
  });

  // — editing a tour (meta + seats) —
  const [editingId, setEditingId]             = useState(null);
  const [editingTourData, setEditingTourData] = useState({
    route_id: "", pricelist_id: "", date: "", layout_variant: ""
  });
  const [initialSeats, setInitialSeats] = useState([]);
  const [seatEdits, setSeatEdits]       = useState({});

  // — sold‐tickets table —
  const [tickets, setTickets]                 = useState([]);
  const [editingTicketId, setEditingTicketId] = useState(null);
  const [editingTicketData, setEditingTicketData] = useState({
    passenger_name: "",
    passenger_phone: "",
    passenger_email: "",
    departure_stop_id: "",
    arrival_stop_id: ""
  });

  // — force‐reload key for SeatAdmin —
  const [seatReload, setSeatReload] = useState(0);

  // — icon button styles —
  const iconBtn = {
    width:40, height:40, margin:"0 4px", padding:0,
    backgroundColor:"#f0f0f5", border:"1px solid #ccc",
    borderRadius:4, display:"inline-flex", alignItems:"center",
    justifyContent:"center", cursor:"pointer",
    transition:"background-color .2s, transform .1s"
  };
  const iconImg = { width:20, height:20 };

  // — load reference data + tours —
  useEffect(() => {
    axios.get(`${API}/tours`).then(r=>setTours(r.data)).catch(console.error);
    axios.get(`${API}/routes`).then(r=>setRoutes(r.data)).catch(console.error);
    axios.get(`${API}/pricelists`).then(r=>setPricelists(r.data)).catch(console.error);
    axios.get(`${API}/stops`).then(r=>setStops(r.data)).catch(console.error);
  }, []);

  // — new‐tour seat toggler —
  const toggleSeatNew = seatNum => {
    setNewTour(prev => ({
      ...prev,
      activeSeats: prev.activeSeats.includes(seatNum)
        ? prev.activeSeats.filter(n => n!==seatNum)
        : [...prev.activeSeats, seatNum]
    }));
  };

  // — create tour —
  const handleCreate = e => {
    e.preventDefault();
    axios.post(`${API}/tours`, {
      route_id: +newTour.route_id,
      pricelist_id: +newTour.pricelist_id,
      date: newTour.date,
      layout_variant: +newTour.layout_variant,
      active_seats: newTour.activeSeats
    })
    .then(()=> axios.get(`${API}/tours`))
    .then(r=>setTours(r.data))
    .catch(console.error)
    .finally(()=> setNewTour({ route_id:"", pricelist_id:"", date:"", layout_variant:"", activeSeats:[] }));
  };

  // — delete tour —
  const handleDelete = id => {
    axios.delete(`${API}/tours/${id}`)
      .then(()=> setTours(ts=>ts.filter(t=>t.id!==id)))
      .catch(console.error);
  };

  // — start editing tour (load seats + tickets) —
  const startEdit = tour => {
    setEditingId(tour.id);
    setEditingTourData({
      route_id: String(tour.route_id),
      pricelist_id: String(tour.pricelist_id),
      date: tour.date,
      layout_variant: String(tour.layout_variant)
    });
    setSeatEdits({});

    // load seat statuses
    axios.get(`${API}/seat`, { params:{ tour_id: tour.id, adminMode:1 } })
      .then(r=>setInitialSeats(r.data.seats))
      .catch(console.error);

    // load sold tickets
    axios.get(`${API}/admin/tickets`, { params:{ tour_id: tour.id } })
      .then(r=>setTickets(r.data))
      .catch(console.error);

    // bump reload so SeatAdmin remounts
    setSeatReload(x=>x+1);
  };

  // — toggle block/unblock locally —
  const toggleSeatEdit = seatNum => {
    setSeatEdits(prev => {
      const wasBlocked = initialSeats.find(s=>s.seat_num===seatNum)?.status==="blocked";
      const curr = prev.hasOwnProperty(seatNum) ? prev[seatNum] : wasBlocked;
      return { ...prev, [seatNum]: !curr };
    });
  };

  // — save tour + seats changes —
  const saveEdit = async () => {
    try {
      const finalActive = initialSeats
        .filter(s=>s.status!=="occupied")
        .filter(s=>{
          if(seatEdits.hasOwnProperty(s.seat_num)){
            return !seatEdits[s.seat_num];
          }
          return s.status!=="blocked";
        })
        .map(s=>s.seat_num);

      await axios.put(`${API}/tours/${editingId}`, {
        route_id:+editingTourData.route_id,
        pricelist_id:+editingTourData.pricelist_id,
        date:editingTourData.date,
        layout_variant:+editingTourData.layout_variant,
        active_seats: finalActive
      });

      const r = await axios.get(`${API}/tours`);
      setTours(r.data);
      setEditingId(null);
    } catch(err) {
      console.error("Ошибка сохранения тура:",err);
    }
  };
  const cancelEdit = () => setEditingId(null);

  // — start editing a ticket row —
  const startTicketEdit = ticket => {
    setEditingTicketId(ticket.ticket_id);
    setEditingTicketData({
      passenger_name: ticket.passenger_name,
      passenger_phone: ticket.passenger_phone,
      passenger_email: ticket.passenger_email,
      departure_stop_id: ticket.departure_stop_id,
      arrival_stop_id: ticket.arrival_stop_id
    });
  };
  const cancelTicketEdit = () => setEditingTicketId(null);

  // — save ticket edits —
  const saveTicketEdit = async () => {
    try {
      await axios.put(`${API}/admin/tickets/${editingTicketId}`, editingTicketData);
      const r = await axios.get(`${API}/admin/tickets`, { params:{ tour_id: editingId }});
      setTickets(r.data);
      setEditingTicketId(null);
    } catch(err) {
      console.error("Ошибка обновления билета:", err);
      alert(err.response?.data?.detail || err.message);
    }
  };

  // — reassign passenger (red→red or red→green/grey) —
  const handleReassign = async (fromSeat, toSeat) => {
    try {
      await axios.post(`${API}/tickets/reassign`, {
        tour_id: editingId,
        from_seat: fromSeat,
        to_seat: toSeat
      });
      setSeatReload(x=>x+1);
      const r = await axios.get(`${API}/admin/tickets`, { params:{ tour_id: editingId }});
      setTickets(r.data);
    } catch(err) {
      console.error("Reassign error:", err);
      alert(err.response?.data?.detail || err.message);
    }
  };

  // — remove ticket when dragged off — calls DELETE /admin/tickets/{ticket_id} —
  const handleRemove = async seatNum => {
    try {
      const tk = tickets.find(t => t.seat_num === seatNum);
      if (!tk) throw new Error("Ticket not found for seat " + seatNum);

      await axios.delete(`${API}/admin/tickets/${tk.ticket_id}`);
      setSeatReload(x=>x+1);
      const r = await axios.get(`${API}/admin/tickets`, { params:{ tour_id: editingId }});
      setTickets(r.data);
    } catch(err) {
      console.error("Remove error:", err);
      alert(err.response?.data?.detail || err.message);
    }
  };

  return (
    <div className="container">
      <h2>Рейсы</h2>

      {/* — Tours list — */}
      <table className="styled-table">
        <thead>
          <tr>
            <th>Маршрут</th><th>Прайс-лист</th><th>Дата</th><th>Вариант</th><th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {tours.map(t => {
            const editing = t.id === editingId;
            return (
              <tr key={t.id}>
                <td>
                  {editing
                    ? <select
                        value={editingTourData.route_id}
                        onChange={e=>setEditingTourData({...editingTourData,route_id:e.target.value})}
                      >
                        <option value="">—</option>
                        {routes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}
                      </select>
                    : routes.find(r=>r.id===t.route_id)?.name || "-"
                  }
                </td>
                <td>
                  {editing
                    ? <select
                        value={editingTourData.pricelist_id}
                        onChange={e=>setEditingTourData({...editingTourData,pricelist_id:e.target.value})}
                      >
                        <option value="">—</option>
                        {pricelists.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    : pricelists.find(p=>p.id===t.pricelist_id)?.name || "-"
                  }
                </td>
                <td>
                  {editing
                    ? <input
                        type="date"
                        value={editingTourData.date}
                        onChange={e=>setEditingTourData({...editingTourData,date:e.target.value})}
                      />
                    : t.date
                  }
                </td>
                <td>
                  {editing
                    ? <select
                        value={editingTourData.layout_variant}
                        onChange={e=>setEditingTourData({...editingTourData,layout_variant:e.target.value})}
                      >
                        <option value="">—</option>
                        <option value="1">Neoplan</option>
                        <option value="2">Travego</option>
                      </select>
                    : (t.layout_variant===1 ? "Neoplan":"Travego")
                  }
                </td>
                <td>
                  {editing
                    ? <>
                        <button style={iconBtn} onClick={saveEdit}>
                          <img style={iconImg} src={saveIcon} alt="Save"/>
                        </button>
                        <button style={iconBtn} onClick={cancelEdit}>
                          <img style={iconImg} src={cancelIcon} alt="Cancel"/>
                        </button>
                      </>
                    : <>
                        <button style={iconBtn} onClick={()=>startEdit(t)}>
                          <img style={iconImg} src={editIcon} alt="Edit"/>
                        </button>
                        <button style={iconBtn} onClick={()=>handleDelete(t.id)}>
                          <img style={iconImg} src={deleteIcon} alt="Delete"/>
                        </button>
                      </>
                  }
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* — SeatAdmin with drag‐n‐drop — */}
      {editingId && (
        <div style={{ marginTop:20 }}>
          <h3>Управление местами</h3>
          <SeatAdmin
            key={seatReload}
            tourId={editingId}
            layoutVariant={+editingTourData.layout_variant}
            seatEdits={seatEdits}
            onToggle={toggleSeatEdit}
            onReassign={handleReassign}
            onRemove={handleRemove}
          />
        </div>
      )}

      {/* — Sold tickets table — */}
      {editingId && (
        <div style={{ marginTop:30 }}>
          <h3>Проданные билеты</h3>
          <table className="styled-table">
            <thead>
              <tr>
                <th>Место</th><th>Имя</th><th>Телефон</th><th>Email</th>
                <th>Отправление</th><th>Прибытие</th><th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map(ticket => {
                const isEd = ticket.ticket_id === editingTicketId;
                return (
                  <tr key={ticket.ticket_id}>
                    <td>{ticket.seat_num}</td>
                    <td>
                      {isEd
                        ? <input
                            value={editingTicketData.passenger_name}
                            onChange={e=>setEditingTicketData({...editingTicketData,passenger_name:e.target.value})}
                          />
                        : ticket.passenger_name
                      }
                    </td>
                    <td>
                      {isEd
                        ? <input
                            value={editingTicketData.passenger_phone}
                            onChange={e=>setEditingTicketData({...editingTicketData,passenger_phone:e.target.value})}
                          />
                        : ticket.passenger_phone
                      }
                    </td>
                    <td>
                      {isEd
                        ? <input
                            value={editingTicketData.passenger_email}
                            onChange={e=>setEditingTicketData({...editingTicketData,passenger_email:e.target.value})}
                          />
                        : ticket.passenger_email
                      }
                    </td>
                    <td>
                      {isEd
                        ? <select
                            value={editingTicketData.departure_stop_id}
                            onChange={e=>setEditingTicketData({...editingTicketData,departure_stop_id:+e.target.value})}
                          >
                            <option value="">—</option>
                            {stops.map(s=><option key={s.id} value={s.id}>{s.stop_name}</option>)}
                          </select>
                        : stopsMap[ticket.departure_stop_id] || ticket.departure_stop_id
                      }
                    </td>
                    <td>
                      {isEd
                        ? <select
                            value={editingTicketData.arrival_stop_id}
                            onChange={e=>setEditingTicketData({...editingTicketData,arrival_stop_id:+e.target.value})}
                          >
                            <option value="">—</option>
                            {stops.map(s=><option key={s.id} value={s.id}>{s.stop_name}</option>)}
                          </select>
                        : stopsMap[ticket.arrival_stop_id] || ticket.arrival_stop_id
                      }
                    </td>
                    <td>
                      {isEd
                        ? <>
                            <button style={iconBtn} onClick={saveTicketEdit}>
                              <img style={iconImg} src={saveIcon} alt="Save"/>
                            </button>
                            <button style={iconBtn} onClick={cancelTicketEdit}>
                              <img style={iconImg} src={cancelIcon} alt="Cancel"/>
                            </button>
                          </>
                        : <button style={iconBtn} onClick={()=>startTicketEdit(ticket)}>
                            <img style={iconImg} src={editIcon} alt="Edit"/>
                          </button>
                      }
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* — new‐tour creation form — */}
      <h3 style={{ marginTop:40 }}>Создать новый рейс</h3>
      <form onSubmit={handleCreate} style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
        <select required
          value={newTour.route_id}
          onChange={e=>setNewTour({...newTour,route_id:e.target.value})}
        >
          <option value="">Маршрут</option>
          {routes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <select required
          value={newTour.pricelist_id}
          onChange={e=>setNewTour({...newTour,pricelist_id:e.target.value})}
        >
          <option value="">Прайс-лист</option>
          {pricelists.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input required type="date"
          value={newTour.date}
          onChange={e=>setNewTour({...newTour,date:e.target.value})}
        />
        <select required
          value={newTour.layout_variant}
          onChange={e=>setNewTour({...newTour,layout_variant:e.target.value})}
        >
          <option value="">Вариант</option>
          <option value="1">Neoplan</option>
          <option value="2">Travego</option>
        </select>
        {newTour.layout_variant && (
          <div style={{ width:"100%", marginTop:8 }}>
            {+newTour.layout_variant===1
              ? <BusLayoutNeoplan
                  seats={[]}
                  selectedSeats={newTour.activeSeats}
                  toggleSeat={toggleSeatNew}
                  interactive
                />
              : <BusLayoutTravego
                  seats={[]}
                  selectedSeats={newTour.activeSeats}
                  toggleSeat={toggleSeatNew}
                  interactive
                />}
          </div>
        )}
        <button type="submit" style={{
          padding:"8px 16px", backgroundColor:"#4caf50",
          color:"#fff", border:"none", borderRadius:4, cursor:"pointer"
        }}>
          Создать рейс
        </button>
      </form>
    </div>
  );
}
