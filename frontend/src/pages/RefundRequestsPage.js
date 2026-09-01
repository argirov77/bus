import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { useSearchParams } from "react-router-dom";
import { API } from "../config";

const formatDateTime = (date) => {
  if (!date) return "—";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ru-RU", { timeZone: "Europe/Sofia", hour12: false });
};

const formatMoney = (amount, currency = "UAH") => {
  if (amount === null || amount === undefined) return "—";
  const num = Number(amount);
  if (Number.isNaN(num)) return "—";
  return `${num.toFixed(2)} ${currency}`;
};

const statusLabel = {
  pending: "Ожидает",
  processing: "В обработке",
  completed: "Завершено",
  failed: "Ошибка",
  rejected: "Отклонено",
};

export default function RefundRequestsPage() {
  useEffect(() => {
    document.title = "Заявки на возврат";
  }, []);

  // Deep link from the purchases page: ?purchase=114 opens that order's request.
  const [searchParams] = useSearchParams();
  const purchaseParam = Number(searchParams.get("purchase")) || null;
  const autoSelected = useRef(false);

  const [requests, setRequests] = useState([]);
  const [listLoaded, setListLoaded] = useState(false);
  const [filter, setFilter] = useState(purchaseParam ? "" : "pending");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [selectedTickets, setSelectedTickets] = useState({});
  const [refundAmount, setRefundAmount] = useState("");
  const [voidFiscal, setVoidFiscal] = useState(true);
  const [comment, setComment] = useState("");
  const [rejectReason, setRejectReason] = useState("");

  const loadList = useCallback(({ preserveError = false } = {}) => {
    const params = {};
    if (filter) params.status = filter;
    axios
      .get(`${API}/admin/refund-requests/`, { params })
      .then((res) => {
        setRequests(res.data || []);
        setListLoaded(true);
        // A refresh triggered by a failed action must not wipe its message.
        if (!preserveError) setError(null);
      })
      .catch((err) => {
        console.error(err);
        setListLoaded(true);
        setError("Не удалось загрузить заявки");
      });
  }, [filter]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const loadDetail = useCallback((id, { preserveForm = false } = {}) => {
    if (id == null) {
      setDetail(null);
      return;
    }
    setDetailError(null);
    axios
      .get(`${API}/admin/refund-requests/${id}`)
      .then((res) => {
        setDetail(res.data);
        // Keep what the admin typed when we are only refreshing the status
        // after a failed attempt — they will retry with the same values.
        if (preserveForm) return;
        const ticketIds = (res.data?.request?.ticket_ids || []);
        const sel = {};
        (res.data?.tickets || []).forEach((t) => {
          sel[t.id] = ticketIds.includes(t.id);
        });
        setSelectedTickets(sel);
        setRefundAmount(
          res.data?.request?.amount_requested != null
            ? String(res.data.request.amount_requested)
            : ""
        );
        setVoidFiscal(true);
        setComment("");
        setRejectReason("");
      })
      .catch((err) => {
        console.error(err);
        setDetailError("Не удалось загрузить детали заявки");
        setDetail(null);
      });
  }, []);

  useEffect(() => {
    loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (!purchaseParam || autoSelected.current) return;
    const match = requests.find((r) => r.purchase_id === purchaseParam);
    if (match) {
      autoSelected.current = true;
      setSelectedId(match.id);
    }
  }, [requests, purchaseParam]);

  const handleToggleTicket = (ticketId) => {
    setSelectedTickets((prev) => ({ ...prev, [ticketId]: !prev[ticketId] }));
  };

  const selectedTicketIds = useMemo(
    () => Object.entries(selectedTickets).filter(([, v]) => v).map(([k]) => Number(k)),
    [selectedTickets]
  );

  useEffect(() => {
    // Auto-recompute refund amount from selected tickets when admin toggles.
    if (!detail) return;
    const tickets = detail.tickets || [];
    if (selectedTicketIds.length === 0) return;
    if (
      detail.request?.amount_requested != null
      && selectedTicketIds.length === (detail.request.ticket_ids || []).length
      && selectedTicketIds.every((id) => (detail.request.ticket_ids || []).includes(id))
    ) {
      // Match original request — leave the field as-is.
      return;
    }
    const total = tickets
      .filter((t) => selectedTicketIds.includes(t.id))
      .reduce((acc, t) => {
        const extra = Number(t.extra_baggage || 0);
        return acc + 0; // server is the source of truth; admin can override
      }, 0);
    if (total > 0) {
      setRefundAmount(String(total.toFixed(2)));
    }
  }, [selectedTicketIds, detail]);

  const handleProcess = () => {
    if (!selectedId) return;
    if (!refundAmount || Number(refundAmount) <= 0) {
      setError("Введите сумму возврата");
      return;
    }
    setBusy(true);
    setError(null);
    axios
      .post(`${API}/admin/refund-requests/${selectedId}/process`, {
        ticket_ids: selectedTicketIds,
        refund_amount: Number(refundAmount),
        void_fiscal: voidFiscal,
        comment: comment || null,
      })
      .then(() => {
        loadList();
        loadDetail(selectedId);
      })
      .catch((err) => {
        console.error(err);
        const msg = err?.response?.data?.detail || "Не удалось обработать возврат";
        setError(String(msg));
        // The request moved to "failed" server-side — refresh so the status and
        // the stored failure reason match reality instead of staying "pending".
        loadList({ preserveError: true });
        loadDetail(selectedId, { preserveForm: true });
      })
      .finally(() => setBusy(false));
  };

  const handleReject = () => {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    axios
      .post(`${API}/admin/refund-requests/${selectedId}/reject`, {
        reason: rejectReason || null,
      })
      .then(() => {
        loadList();
        loadDetail(selectedId);
      })
      .catch((err) => {
        console.error(err);
        const msg = err?.response?.data?.detail || "Не удалось отклонить заявку";
        setError(String(msg));
      })
      .finally(() => setBusy(false));
  };

  const pendingCount = requests.filter((r) => r.status === "pending").length;
  const request = detail?.request;
  const isPending = request?.status === "pending";
  // A failed request can be retried: the backend skips the LiqPay/CheckBox
  // steps that already succeeded, so re-processing never refunds twice.
  const canProcess = isPending || request?.status === "failed";

  return (
    <div style={{ padding: 16 }}>
      <h2>Заявки на возврат {pendingCount > 0 && <span style={{ background: "#d4a000", color: "#fff", borderRadius: 12, padding: "2px 8px", fontSize: 14 }}>{pendingCount}</span>}</h2>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {["pending", "processing", "completed", "failed", "rejected", ""].map((s) => (
          <button
            key={s || "all"}
            className="btn btn--sm"
            onClick={() => { setFilter(s); setSelectedId(null); }}
            style={{
              fontWeight: filter === s ? 700 : 400,
              textDecoration: filter === s ? "underline" : "none",
            }}
          >
            {s ? (statusLabel[s] || s) : "Все"}
          </button>
        ))}
      </div>

      {error && <div style={{ color: "red", marginBottom: 8 }}>{error}</div>}
      {purchaseParam
        && listLoaded
        && !requests.some((r) => r.purchase_id === purchaseParam) && (
        <div style={{ color: "#a15c00", marginBottom: 8 }}>
          По заказу #{purchaseParam} заявок на возврат не найдено — клиент ещё
          не оформил заявку.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>#</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>Заказ</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>Клиент</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>Билеты</th>
                <th style={{ textAlign: "right", borderBottom: "1px solid #ccc" }}>Сумма</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>Статус</th>
                <th style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>Дата</th>
              </tr>
            </thead>
            <tbody>
              {requests.length === 0 && (
                <tr>
                  <td colSpan="7" style={{ padding: 16, textAlign: "center", color: "#888" }}>
                    Нет заявок
                  </td>
                </tr>
              )}
              {requests.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  style={{
                    cursor: "pointer",
                    background: r.id === selectedId ? "#f0f7ff" : "transparent",
                  }}
                >
                  <td>{r.id}</td>
                  <td>#{r.purchase_id}</td>
                  <td>
                    {r.customer_name || "—"}
                    <br />
                    <small style={{ color: "#666" }}>{r.customer_email || ""}</small>
                  </td>
                  <td>{(r.ticket_ids || []).join(", ") || "все"}</td>
                  <td style={{ textAlign: "right" }}>
                    {formatMoney(r.amount_requested, r.currency)}
                  </td>
                  <td>{statusLabel[r.status] || r.status}</td>
                  <td>{formatDateTime(r.requested_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          {!detail && (
            <div style={{ color: "#888" }}>
              {detailError || "Выберите заявку слева"}
            </div>
          )}
          {detail && (
            <div>
              <h3>Заявка #{request.id}</h3>
              <div>Заказ: #{detail.request.purchase_id}</div>
              <div>Клиент: {request.customer_name || "—"} ({request.customer_email || "—"})</div>
              <div>Способ оплаты: {detail.payment_method || "—"}</div>
              <div>Оплачено всего: {formatMoney(detail.paid_amount)}</div>
              <div>
                <strong>Осталось доступно к возврату: {formatMoney(detail.remaining)}</strong>
              </div>
              {request.reason && (
                <div style={{ marginTop: 8 }}>
                  <em>Причина клиента:</em> {request.reason}
                </div>
              )}

              <h4 style={{ marginTop: 16 }}>Билеты</h4>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th></th>
                    <th>#</th>
                    <th>Пассажир</th>
                    <th>Откуда</th>
                    <th>Куда</th>
                    <th>Дата</th>
                    <th>Место</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.tickets || []).map((t) => (
                    <tr key={t.id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={!!selectedTickets[t.id]}
                          disabled={!canProcess}
                          onChange={() => handleToggleTicket(t.id)}
                        />
                      </td>
                      <td>{t.id}</td>
                      <td>{t.passenger_name || "—"}</td>
                      <td>{t.from_stop_name || "—"}</td>
                      <td>{t.to_stop_name || "—"}</td>
                      <td>{t.tour_date || "—"}</td>
                      <td>{t.seat_num ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {canProcess ? (
                <div style={{ marginTop: 16, display: "grid", gap: 8 }}>
                  {request.failure_reason && (
                    <div style={{ color: "red" }}>
                      Прошлая попытка не удалась: {request.failure_reason}
                    </div>
                  )}
                  <label>
                    Сумма возврата:&nbsp;
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={refundAmount}
                      onChange={(e) => setRefundAmount(e.target.value)}
                      style={{ width: 120 }}
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={voidFiscal}
                      onChange={(e) => setVoidFiscal(e.target.checked)}
                    />
                    &nbsp;Оформить фискальный возврат (CheckBox)
                  </label>
                  <label>
                    Комментарий:&nbsp;
                    <input
                      type="text"
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      style={{ width: 320 }}
                    />
                  </label>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn btn--primary"
                      onClick={handleProcess}
                      disabled={
                        busy
                        || !detail.liqpay_order_id
                        || selectedTicketIds.length === 0
                      }
                      title={!detail.liqpay_order_id ? "Только для оплат через LiqPay" : ""}
                    >
                      {busy
                        ? "Обработка..."
                        : isPending
                          ? "Вернуть через LiqPay"
                          : "Повторить возврат"}
                    </button>
                    {isPending && request.requested_by === "customer" && (
                      <>
                        <input
                          type="text"
                          placeholder="Причина отказа"
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                          style={{ width: 220 }}
                        />
                        <button
                          className="btn btn--ghost"
                          onClick={handleReject}
                          disabled={busy}
                        >
                          Отклонить заявку
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: 16, color: "#666" }}>
                  Заявка в статусе <strong>{statusLabel[request.status] || request.status}</strong>.
                  {request.amount_refunded != null && (
                    <div>Возвращено: {formatMoney(request.amount_refunded, request.currency)}</div>
                  )}
                  {request.failure_reason && (
                    <div style={{ color: "red" }}>Ошибка: {request.failure_reason}</div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
