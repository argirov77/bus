import React, { useState, useEffect } from "react";
import axios from "axios";

import { API } from "../config";

export default function TicketsAdmin({ tourId }) {
  const [tickets,   setTickets]   = useState([]);
  const [stopsMap,  setStopsMap]  = useState({});

  // загрузить проданные билеты
  const loadTickets = ()=>{
    axios.get(`${API}/admin/tickets`,{params:{tour_id:tourId}})
      .then(r=>setTickets(r.data));
  };

  // загрузить все остановки (для маппинга id→name)
  useEffect(()=>{
    axios.get(`${API}/stops`)
      .then(r=>{
        const m = {};
        r.data.forEach(s=>m[s.id]=s.stop_name);
        setStopsMap(m);
      });
  },[]);

  useEffect(loadTickets,[tourId]);

  const updateField = (ticketId, field, value) => {
    axios.put(`${API}/admin/tickets/${ticketId}`,{ [field]:value })
      .then(loadTickets);
  };

  return (
    <div style={{marginTop:20}}>
      <h4>Проданные билеты</h4>
      <table className="styled-table">
        <thead>
          <tr>
            <th>№ билета</th>
            <th>Место</th>
            <th>Имя</th>
            <th>Телефон</th>
            <th>Email</th>
            <th>Откуда → Куда</th>
            <th>Багаж</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map(t=>(
            <tr key={t.ticket_id}>
              <td>{t.ticket_id}</td>
              <td>{t.seat_num}</td>
              <td>
                <input
                  value={t.passenger_name}
                  onChange={e=>updateField(t.ticket_id,"passenger_name",e.target.value)}
                />
              </td>
              <td>
                <input
                  value={t.passenger_phone}
                  onChange={e=>updateField(t.ticket_id,"passenger_phone",e.target.value)}
                />
              </td>
              <td>
                <input
                  value={t.passenger_email}
                  onChange={e=>updateField(t.ticket_id,"passenger_email",e.target.value)}
                />
              </td>
              <td>
                {stopsMap[t.departure_stop_id]||t.departure_stop_id}
                {" → "}
                {stopsMap[t.arrival_stop_id]  ||t.arrival_stop_id}
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={t.extra_baggage}
                  onChange={e=>updateField(t.ticket_id,"extra_baggage",e.target.checked)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
