// src/pages/ToursPage.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import { API } from "../config";

import BusLayoutNeoplan from "../components/busLayouts/BusLayoutNeoplan";
import BusLayoutTravego  from "../components/busLayouts/BusLayoutTravego";
import SeatAdmin         from "../components/SeatAdmin";


const BOOKING_OPTIONS = [
  { value: 0, label: "Сгорает через 48 ч после бронирования" },
  { value: 1, label: "Сгорает за 48 ч до выезда" },
  { value: 2, label: "Не сгорает (оплата при посадке)" },
  { value: 3, label: "Бронировать нельзя (только оплата)" },
];

export default function ToursPage() {
  // — reference data —
  const [tours, setTours]           = useState([]);
  const [routes, setRoutes]         = useState([]);
  const [pricelists, setPricelists] = useState([]);
  const [stops, setStops]           = useState([]);
  const stopsMap = Object.fromEntries(stops.map(s => [s.id, s.stop_name]));

  const PAGE_SIZE = 10;
  const [tab, setTab]       = useState('upcoming');
  const [page, setPage]     = useState(1);
  const [total, setTotal]   = useState(0);
  const [filterDate, setFilterDate]       = useState("");
  const [filterRoute, setFilterRoute]     = useState("");
  const [filterBooking, setFilterBooking] = useState("");
  const [showForm, setShowForm] = useState(false);
  const totalPages = Math.ceil(total / PAGE_SIZE);

  // — new‐tour form state —
  const [newTour, setNewTour] = useState({
    route_id: "", pricelist_id: "", date: "", layout_variant: "", booking_terms: "", activeSeats: []
  });

  // — editing a tour (meta + seats) —
  const [editingId, setEditingId]             = useState(null);
  const [editingTourData, setEditingTourData] = useState({
    route_id: "", pricelist_id: "", date: "", layout_variant: "", booking_terms: ""
  });
  const [initialSeats, setInitialSeats] = useState([]);
  const [seatEdits, setSeatEdits]       = useState({});

  // — sold‐tickets table —
  const [tickets, setTickets]                 = useState([]);
  const [editingTicketId, setEditingTicketId] = useState(null);
  const [editingTicketData, setEditingTicketData] = useState({
    passenger_name: "",
    departure_stop_id: "",
    arrival_stop_id: "",
    extra_baggage: false
  });

  // — force‐reload key for SeatAdmin —
  const [seatReload, setSeatReload] = useState(0);

  const fetchTours = (pageParam = page) => {
    const params = {
      page: pageParam,
      page_size: PAGE_SIZE,
      show_past: tab === 'past'
    };
    if (filterDate) params.date = filterDate;
    if (filterRoute) params.route_id = filterRoute;
    if (filterBooking) params.booking_terms = filterBooking;
    return axios.get(`${API}/tours/list`, { params })
      .then(r=>{ setTours(r.data.items); setTotal(r.data.total); })
      .catch(console.error);
  };

  const applyFilters = e => {
    e.preventDefault();
    setPage(1);
    fetchTours(1);
  };

  const switchTab = t => {
    setTab(t);
    setPage(1);
  };

  // — load reference data on mount —
  useEffect(() => {
    axios.get(`${API}/routes`).then(r=>setRoutes(r.data)).catch(console.error);
    axios.get(`${API}/pricelists`).then(r=>setPricelists(r.data)).catch(console.error);
    axios.get(`${API}/stops`).then(r=>setStops(r.data)).catch(console.error);
    fetchTours(1);
  }, []);

  // — refetch tours when tab/page changes —
  useEffect(() => {
    fetchTours();
  }, [tab, page]);

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
      booking_terms: +newTour.booking_terms,
      active_seats: newTour.activeSeats
    })
    .then(()=> fetchTours(1))
    .catch(console.error)
    .finally(()=> {
      setNewTour({ route_id:"", pricelist_id:"", date:"", layout_variant:"", booking_terms:"", activeSeats:[] });
      setShowForm(false);
      setPage(1);
    });
  };

  // — delete tour —
  const handleDelete = id => {
    axios.delete(`${API}/tours/${id}`)
      .then(()=> fetchTours())
      .catch(console.error);
  };

  // — start editing tour (load seats + tickets) —
  const startEdit = tour => {
    setEditingId(tour.id);
    setEditingTourData({
      route_id: String(tour.route_id),
      pricelist_id: String(tour.pricelist_id),
      date: tour.date,
      layout_variant: String(tour.layout_variant),
      booking_terms: String(tour.booking_terms)
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
        booking_terms:+editingTourData.booking_terms,
        active_seats: finalActive
      });

      await fetchTours();
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
      departure_stop_id: ticket.departure_stop_id,
      arrival_stop_id: ticket.arrival_stop_id,
      extra_baggage: ticket.extra_baggage
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

      <div style={{ margin: '16px 0' }}>
        <button className="btn btn--ghost btn--sm" onClick={()=>switchTab('upcoming')} disabled={tab==='upcoming'}>Предстоящие</button>
        <button className="btn btn--ghost btn--sm" onClick={()=>switchTab('past')} disabled={tab==='past'} style={{marginLeft:8}}>Прошедшие</button>
      </div>

      <form onSubmit={applyFilters} style={{ display:'flex', gap:8, flexWrap:'wrap', marginBottom:20 }}>
        <input className="input" type="date" value={filterDate} onChange={e=>setFilterDate(e.target.value)} />
        <select className="input" value={filterRoute} onChange={e=>setFilterRoute(e.target.value)}>
          <option value="">Маршрут</option>
          {routes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <select className="input" value={filterBooking} onChange={e=>setFilterBooking(e.target.value)}>
          <option value="">Условия брони</option>
          {BOOKING_OPTIONS.map(o=>(<option key={o.value} value={o.value}>{o.label}</option>))}
        </select>
        <button type="submit" className="btn btn--primary btn--sm">Поиск</button>
      </form>

      {/* — Tours list — */}
      <table className="styled-table">
        <thead>
          <tr>
            <th>Маршрут</th><th>Прайс-лист</th><th>Дата</th><th>Вариант</th><th>Бронь</th><th>Действия</th>
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
                        className="input"
                        value={editingTourData.route_id}
                        onChange={e=>setEditingTourData({...editingTourData,route_id:e.target.value})}
                      >
                        <option value="">—</option>
                        {routes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}
                      </select>
                    : <span className="chip chip--route">{routes.find(r=>r.id===t.route_id)?.name || "-"}</span>
                  }
                </td>
                <td>
                  {editing
                    ? <select
                        className="input"
                        value={editingTourData.pricelist_id}
                        onChange={e=>setEditingTourData({...editingTourData,pricelist_id:e.target.value})}
                      >
                        <option value="">—</option>
                        {pricelists.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    : <span className="chip chip--price">{pricelists.find(p=>p.id===t.pricelist_id)?.name || "-"}</span>
                  }
                </td>
                <td>
                  {editing
                    ? <input
                        className="input"
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
                        className="input"
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
                    ? <select
                        className="input"
                        value={editingTourData.booking_terms}
                        onChange={e=>setEditingTourData({...editingTourData,booking_terms:e.target.value})}
                      >
                        <option value="">—</option>
                        {BOOKING_OPTIONS.map(o=>(<option key={o.value} value={o.value}>{o.label}</option>))}
                      </select>
                    : (BOOKING_OPTIONS.find(o=>o.value===t.booking_terms)?.label || t.booking_terms)
                  }
                </td>
                <td>
                  {editing
                    ? <>
                        <button className="btn btn--primary btn--sm" onClick={saveEdit}>Сохранить</button>
                        <button className="btn btn--ghost btn--sm" onClick={cancelEdit}>Отмена</button>
                      </>
                    : <>
                        <button className="btn btn--primary btn--sm" onClick={()=>startEdit(t)}>Редактировать</button>
                        <button className="btn btn--danger btn--sm" onClick={()=>handleDelete(t.id)}>Удалить</button>
                      </>
                  }
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ margin: '16px 0', display:'flex', alignItems:'center', gap:4 }}>
        <button className="btn btn--sm" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Назад</button>
        {Array.from({length: totalPages}, (_, i) => (
          <button
            className="btn btn--sm"
            key={i+1}
            disabled={page===i+1}
            onClick={()=>setPage(i+1)}
          >{i+1}</button>
        ))}
        <button className="btn btn--sm" disabled={page===totalPages || totalPages===0} onClick={()=>setPage(p=>p+1)}>Вперёд</button>
      </div>

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
                <th>Место</th>
                <th>Имя</th>
                <th>Отправление</th>
                <th>Прибытие</th>
                <th>Багаж</th>
                <th>Действия</th>
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
                        ? <input
                            type="checkbox"
                            checked={editingTicketData.extra_baggage}
                            onChange={e=>setEditingTicketData({...editingTicketData,extra_baggage:e.target.checked})}
                          />
                        : (ticket.extra_baggage ? '✔' : '')
                      }
                    </td>
                    <td>
                      {isEd
                        ? <>
                            <button className="btn btn--primary btn--sm" onClick={saveTicketEdit}>Сохранить</button>
                            <button className="btn btn--ghost btn--sm" onClick={cancelTicketEdit}>Отмена</button>
                          </>
                        : <button className="btn btn--primary btn--sm" onClick={()=>startTicketEdit(ticket)}>Редактировать</button>
                      }
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

        <div style={{ marginTop:40 }}>
          <button className="btn btn--primary" onClick={()=>setShowForm(s=>!s)}>{showForm ? 'Скрыть форму' : 'Добавить рейс'}</button>
          {showForm && (
            <>
              <h3 style={{ marginTop:20 }}>Создать новый рейс</h3>
              <form onSubmit={handleCreate} style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                <select className="input" required
                  value={newTour.route_id}
                  onChange={e=>setNewTour({...newTour,route_id:e.target.value})}
                >
                  <option value="">Маршрут</option>
                  {routes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
                <select className="input" required
                  value={newTour.pricelist_id}
                  onChange={e=>setNewTour({...newTour,pricelist_id:e.target.value})}
                >
                  <option value="">Прайс-лист</option>
                  {pricelists.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <input className="input" required type="date"
                  value={newTour.date}
                  onChange={e=>setNewTour({...newTour,date:e.target.value})}
                />
                <select className="input" required
                  value={newTour.booking_terms}
                  onChange={e=>setNewTour({...newTour,booking_terms:e.target.value})}
                >
                  <option value="">Условия брони</option>
                  {BOOKING_OPTIONS.map(o=>(<option key={o.value} value={o.value}>{o.label}</option>))}
                </select>
                <select className="input" required
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
                <button type="submit" className="btn btn--success">Создать рейс</button>
              </form>
            </>
          )}
        </div>
    </div>
  );
}
