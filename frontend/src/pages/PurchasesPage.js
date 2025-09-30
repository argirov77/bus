import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../config";
import { downloadTicketPdf } from "../utils/ticket";
import "../styles/PurchasesPage.css";

const EMPTY_TOTALS = { pax_count: 0, baggage_count: 0, hand_baggage_count: 0 };

const formatDateShort = (date) => {
  if (!date) return "";
  const d = new Date(date);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
};

const normalizePurchaseDetails = (details) => {
  if (!details || typeof details !== "object") {
    return { tickets: [], logs: [], totals: { ...EMPTY_TOTALS } };
  }

  const tickets = Array.isArray(details.tickets) ? details.tickets : [];
  const logs = Array.isArray(details.logs) ? details.logs : [];

  const rawTotals = details.totals && typeof details.totals === "object" ? details.totals : {};
  const totals = {
    pax_count: Number.isFinite(rawTotals.pax_count) ? rawTotals.pax_count : 0,
    baggage_count: Number.isFinite(rawTotals.baggage_count) ? rawTotals.baggage_count : 0,
    hand_baggage_count: Number.isFinite(rawTotals.hand_baggage_count)
      ? rawTotals.hand_baggage_count
      : 0,
  };

  return { ...details, tickets, logs, totals };
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
                map[p.id] = normalizePurchaseDetails(res.data);
              })
              .catch((err) => {
                console.error(err);
                map[p.id] = normalizePurchaseDetails();
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

  const handleTicketDownload = async (ticketId) => {
    try {
      await downloadTicketPdf(ticketId);
    } catch (err) {
      console.error("Не удалось скачать билет", err);
      window.alert("Не удалось скачать билет. Попробуйте ещё раз.");
    }
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
          {items.map((p) => {
            const details = info[p.id];
            const tickets = details?.tickets ?? [];
            const logs = details?.logs ?? [];
            const totals = details?.totals ?? { ...EMPTY_TOTALS };

            const passengerCount = tickets.length
              ? Array.from(new Set(tickets.map((t) => t.passenger_id))).length
              : "";
            const ticketCount = tickets.length || "";
            const tourDates = tickets.length
              ? Array.from(new Set(tickets.map((t) => formatDateShort(t.tour_date)))).join(", ")
              : "";

            return (
              <React.Fragment key={p.id}>
                <tr data-id={p.id}>
                  <td>{p.id}</td>
                  <td>
                    {p.customer_name}<br />
                    {p.customer_phone && <small>{p.customer_phone}<br /></small>}
                    {p.customer_email && <small>{p.customer_email}</small>}
                  </td>
                  <td>{passengerCount}</td>
                  <td>{ticketCount}</td>
                  <td>{tourDates}</td>
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
                {expandedId === p.id && details && (
                  <tr className="details" data-details-for={p.id}>
                    <td colSpan="9">
                      <div className="details-inner">
                        <div className="card">
                          <h4>Билеты</h4>
                          <div className="tag-list">
                            <span className="tag">Пассажиры: {totals.pax_count}</span>
                            <span className="tag">Багаж: {totals.baggage_count}</span>
                            <span className="tag">Ручная кладь: {totals.hand_baggage_count}</span>
                          </div>
                          <table className="table-mini">
                            <thead>
                              <tr>
                                <th>Пассажир</th>
                                <th>Откуда</th>
                                <th>Куда</th>
                                <th>Дата</th>
                                <th>Место</th>
                                <th>Багаж</th>
                                <th>Действия</th>
                              </tr>
                            </thead>
                            <tbody>
                              {tickets.length ? (
                                tickets.map((t) => (
                                  <tr key={t.id}>
                                    <td>{t.passenger_name}</td>
                                    <td>{t.from_stop_name}</td>
                                    <td>{t.to_stop_name}</td>
                                    <td>{formatDateShort(t.tour_date)}</td>
                                    <td>{t.seat_num}</td>
                                    <td>{t.extra_baggage ? "Да" : "—"}</td>
                                    <td>
                                      <button
                                        type="button"
                                        className="btn btn--sm"
                                        onClick={() => handleTicketDownload(t.id)}
                                      >
                                        Скачать
                                      </button>
                                    </td>
                                  </tr>
                                ))
                              ) : (
                                <tr>
                                  <td colSpan="7">Нет билетов</td>
                                </tr>
                              )}
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
                              {logs.length ? (
                                logs.map((l) => (
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
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
