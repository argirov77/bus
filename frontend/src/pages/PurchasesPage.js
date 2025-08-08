import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../config";

const formatDateShort = (date) => {
  if (!date) return "";
  const d = new Date(date);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
};

const formatDateTime = (date) => {
  if (!date) return "";
  const d = new Date(date);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
};

const statusColors = {
  reserved: "orange",
  paid: "green",
  refunded: "red",
  cancelled: "gray",
};

export default function PurchasesPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const [info, setInfo] = useState({});
  const [expanded, setExpanded] = useState({});

  const load = () => {
    const params = {};
    if (status) params.status = status;
    axios
      .get(`${API}/admin/purchases`, { params })
      .then(async (r) => {
        setItems(r.data);
        const map = {};
        await Promise.all(
          r.data.map((p) =>
            axios
              .get(`${API}/admin/purchases/${p.id}`)
              .then((res) => {
                map[p.id] = res.data;
              })
          )
        );
        setInfo(map);
      })
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
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div>
      <h2>Покупки</h2>
      <label>
        Статус:
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Все</option>
          <option value="reserved">reserved</option>
          <option value="paid">paid</option>
          <option value="cancelled">cancelled</option>
          <option value="refunded">refunded</option>
        </select>
      </label>
      <table
        border="1"
        cellPadding="4"
        style={{ marginTop: 10, borderCollapse: "collapse" }}
      >
        <thead>
          <tr>
            <th>№</th>
            <th>Клиент</th>
            <th>Кол-во пассажиров</th>
            <th>Кол-во билетов</th>
            <th>Даты рейсов</th>
            <th>Сумма</th>
            <th>Статус</th>
            <th>Оплата</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <React.Fragment key={p.id}>
              <tr>
                <td>{p.id}</td>
                <td>
                  <div>{p.customer_name}</div>
                  {p.customer_phone && <div>{p.customer_phone}</div>}
                  {p.customer_email && <div>{p.customer_email}</div>}
                </td>
                <td>{p.passenger_count}</td>
                <td>{p.ticket_count}</td>
                <td>{p.tour_dates.map((d) => formatDateShort(d)).join(", ")}</td>
                <td>{p.amount_due}</td>
                <td style={{ color: statusColors[p.status] || "inherit" }}>{p.status}</td>
                <td>{p.payment_method}</td>
                <td>
                  <button onClick={() => toggleInfo(p.id)}>
                    {expanded[p.id] ? "Скрыть" : "Детали"}
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
              {expanded[p.id] && info[p.id] && (
                <tr>
                  <td colSpan="9">
                    <div>
                      <strong>Пассажиры и билеты:</strong>
                      <table border="1" cellPadding="4">
                        <thead>
                          <tr>
                            <th>Пассажир</th>
                            <th>Туда</th>
                            <th>Обратно</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(() => {
                            const byPassenger = {};
                            info[p.id].tickets.forEach((t) => {
                              if (!byPassenger[t.passenger_name]) byPassenger[t.passenger_name] = [];
                              byPassenger[t.passenger_name].push(t);
                            });
                            return Object.entries(byPassenger).map(([name, tickets]) => {
                              tickets.sort(
                                (a, b) => new Date(a.tour_date) - new Date(b.tour_date)
                              );
                              const getIcons = () => {
                                const icons = ["⏳"];
                                if (p.status === "paid") icons.push("💵");
                                if (
                                  info[p.id].sales.some((s) => s.category === "refund")
                                )
                                  icons.push("🔙");
                                return icons.join(" ");
                              };
                              const formatTicket = (tt) =>
                                tt
                                  ? `${formatDateShort(tt.tour_date)}, место ${
                                      tt.seat_num
                                    }, багаж ${tt.extra_baggage ? "✓" : "✗"} ${getIcons()}`
                                  : "";
                              return (
                                <tr key={name}>
                                  <td>{name}</td>
                                  <td>{formatTicket(tickets[0])}</td>
                                  <td>{formatTicket(tickets[1])}</td>
                                </tr>
                              );
                            });
                          })()}
                        </tbody>
                      </table>
                      <strong>Логи (sales):</strong>
                      <table border="1" cellPadding="4">
                        <thead>
                          <tr>
                            <th>Событие</th>
                            <th>Дата/время</th>
                            <th>Способ оплаты</th>
                            <th>Сумма</th>
                          </tr>
                        </thead>
                        <tbody>
                          {info[p.id].sales.map((s) => (
                            <tr key={s.id}>
                              <td>{s.category}</td>
                              <td>{formatDateTime(s.date)}</td>
                              <td>{s.comment || ""}</td>
                              <td>{s.amount}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
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
