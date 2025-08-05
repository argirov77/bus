import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../config";

export default function PurchasesPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");

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
            <tr key={p.id}>
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
              <td>{p.deadline || ""}</td>
              <td>{p.payment_method}</td>
              <td>
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
