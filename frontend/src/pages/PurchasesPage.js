import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../config";
import "../styles/PurchasesPage.css";

const formatDateShort = (date) => {
  if (!date) return "";
  const d = new Date(date);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
};

export default function PurchasesPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const [info, setInfo] = useState({});
  const [expandedId, setExpandedId] = useState(null);

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
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const statusBadge = (s) => <span className={`badge ${s}`}>{s}</span>;

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
      <table className="purchases">
        <thead>
          <tr>
            <th>№</th>
            <th>Клиент</th>
            <th>Пасс.</th>
            <th>Билеты</th>
            <th>Даты</th>
            <th>Сумма</th>
            <th>Статус</th>
            <th>Оплата</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <React.Fragment key={p.id}>
              <tr data-id={p.id}>
                <td>{p.id}</td>
                <td>
                  {p.customer_name}<br />
                  {p.customer_phone && <small>{p.customer_phone}<br /></small>}
                  {p.customer_email && <small>{p.customer_email}</small>}
                </td>
                <td>
                  {info[p.id]
                    ? Array.from(new Set(info[p.id].tickets.map((t) => t.passenger_id))).length
                    : ""}
                </td>
                <td>{info[p.id] ? info[p.id].tickets.length : ""}</td>
                <td>
                  {info[p.id]
                    ? Array.from(new Set(info[p.id].tickets.map((t) => formatDateShort(t.tour_date)))).join(", ")
                    : ""}
                </td>
                <td>{p.amount_due}</td>
                <td>{statusBadge(p.status)}</td>
                <td>{p.payment_method || "-"}</td>
                <td>
                  <button className="btn" onClick={() => toggleInfo(p.id)}>
                    {expandedId === p.id ? "Скрыть" : "Инфо"}
                  </button>
                  {p.status === "reserved" && (
                    <>
                      <button className="btn primary" onClick={() => handlePay(p.id)}>Pay</button>
                      <button className="btn" onClick={() => handleCancel(p.id)}>Cancel</button>
                    </>
                  )}
                  {p.status === "paid" && (
                    <button className="btn" onClick={() => handleRefund(p.id)}>Refund</button>
                  )}
                </td>
              </tr>
              {expandedId === p.id && info[p.id] && (
                <tr className="details" data-details-for={p.id}>
                  <td colSpan="9">
                    <div className="details-inner">
                      <div className="card">
                        <h4>Билеты</h4>
                        <table className="table-mini">
                          <thead>
                            <tr>
                              <th>Пассажир</th>
                              <th>Откуда</th>
                              <th>Куда</th>
                              <th>Дата</th>
                              <th>Место</th>
                              <th>Багаж</th>
                            </tr>
                          </thead>
                          <tbody>
                            {info[p.id].tickets.map((t) => (
                              <tr key={t.id}>
                                <td>{t.passenger_name}</td>
                                <td>{t.from_stop_name}</td>
                                <td>{t.to_stop_name}</td>
                                <td>{formatDateShort(t.tour_date)}</td>
                                <td>{t.seat_num}</td>
                                <td>{t.extra_baggage ? "Да" : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="card">
                        <h4>Логи заказа</h4>
                        <table className="table-mini">
                          <thead>
                            <tr>
                              <th>Действие</th>
                              <th>Дата/время</th>
                              <th>Пользователь</th>
                              <th>Способ</th>
                              <th>Сумма</th>
                            </tr>
                          </thead>
                          <tbody>
                            {info[p.id].logs.length ? (
                              info[p.id].logs.map((l) => (
                                <tr key={l.id}>
                                  <td>{l.action}</td>
                                  <td>{new Date(l.at).toLocaleString('ru-RU', { timeZone: 'Europe/Sofia', hour12: false })}</td>
                                  <td>{l.by || '—'}</td>
                                  <td>{l.method || '—'}</td>
                                  <td>{l.amount}</td>
                                </tr>
                              ))
                            ) : (
                              <tr>
                                <td colSpan="5">Нет действий</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                      <div className="card actions-col">
                        <h4>Действия</h4>
                        <button className="btn" onClick={() => toggleInfo(p.id)}>Скрыть</button>
                        {p.status === "reserved" && (
                          <>
                            <button className="btn primary" onClick={() => handlePay(p.id)}>
                              Отметить оплату (офлайн)
                            </button>
                            <button className="btn" onClick={() => handleCancel(p.id)}>
                              Отменить бронь
                            </button>
                          </>
                        )}
                        {p.status === "paid" && (
                          <button className="btn" onClick={() => handleRefund(p.id)}>
                            Возврат
                          </button>
                        )}
                      </div>
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
