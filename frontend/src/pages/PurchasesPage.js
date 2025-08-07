import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../config";

const formatDeadline = (deadline) => {
  if (!deadline) return "";
  const d = new Date(deadline);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())} ${pad(d.getDate())}/${pad(
    d.getMonth() + 1
  )}/${d.getFullYear()}`;
};

export default function PurchasesPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const [info, setInfo] = useState({});

  const load = () => {
    const params = {};
    if (status) params.status = status;
    axios
      .get(`${API}/admin/purchases`, { params })
      .then((r) => setItems(r.data))
      .catch((e) => console.error(e));
  };

  useEffect(() => {
    load();
  }, [status]);

  const handlePay = (id) => {
    axios.post(`${API}/purchase/${id}/pay`).then(load).catch(console.error);
  };
  const handleCancel = (id) => {
    axios.post(`${API}/purchase/${id}/cancel`).then(load).catch(console.error);
  };
  const handleRefund = (id) => {
    axios.post(`${API}/purchase/${id}/refund`).then(load).catch(console.error);
  };

  const toggleInfo = (id) => {
    if (info[id]) {
      setInfo((prev) => ({ ...prev, [id]: null }));
    } else {
      axios
        .get(`${API}/admin/purchases/${id}`)
        .then((r) => setInfo((prev) => ({ ...prev, [id]: r.data })))
        .catch(console.error);
    }
  };

  return (
    <div>
      <h2>Purchases</h2>
      <label>
        Status:
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          <option value="reserved">reserved</option>
          <option value="paid">paid</option>
          <option value="cancelled">cancelled</option>
          <option value="refunded">refunded</option>
        </select>
      </label>
      <table border="1" cellPadding="4" style={{ marginTop: 10 }}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Client</th>
            <th>Route</th>
            <th>Seats</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Deadline</th>
            <th>Payment</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <React.Fragment key={p.id}>
              <tr>
                <td>{p.id}</td>
                <td>
                  {p.customer_name}
                  <br />
                  {p.customer_email}
                  <br />
                  {p.customer_phone}
                </td>
                <td>
                  {p.tour_date} {p.route_name}
                  <br />
                  {p.departure_stop} - {p.arrival_stop}
                </td>
                <td>{(p.seats || []).join(", ")}</td>
                <td>{p.amount_due}</td>
                <td>{p.status}</td>
                <td>{formatDeadline(p.deadline)}</td>
                <td>{p.payment_method}</td>
                <td>
                  <button onClick={() => toggleInfo(p.id)}>
                    {info[p.id] ? "Hide" : "Info"}
                  </button>
                  {p.status === "reserved" && (
                    <>
                      <button onClick={() => handlePay(p.id)}>Pay</button>
                      <button onClick={() => handleCancel(p.id)}>Cancel</button>
                    </>
                  )}
                  {p.status === "paid" && (
                    <button onClick={() => handleRefund(p.id)}>Refund</button>
                  )}
                </td>
              </tr>
              {info[p.id] && (
                <tr>
                  <td colSpan="9">
                    <strong>Sales:</strong>
                    <ul>
                      {info[p.id].sales.map((s) => (
                        <li key={s.id}>
                          {new Date(s.date).toLocaleString()} {s.category} {s.amount}
                        </li>
                      ))}
                    </ul>
                    <strong>Tickets:</strong>
                    <ul>
                      {info[p.id].tickets.map((t) => (
                        <li key={t.id}>
                          Ticket {t.id}: seat {t.seat_id}, passenger {t.passenger_id}
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
