import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../config";
import { downloadTicketPdf } from "../utils/ticket";
import "../styles/PurchasesPage.css";

const formatDateShort = (date) => {
  if (!date) return "";
  const d = new Date(date);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
};

const formatDateTime = (date) => {
  if (!date) return "";
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", { timeZone: "Europe/Sofia", hour12: false });
};

const statusToneMap = {
  reserved: "warn",
  paid: "ok",
  cancelled: "neutral",
  canceled: "neutral",
  refunded: "neutral",
};

const SCROLL_STORAGE_KEY = "purchases.scrolls.v1";

const makeScrollKey = (orderId, section) => `${orderId}::${section}`;

export default function PurchasesPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [info, setInfo] = useState({});
  const [expandedId, setExpandedId] = useState(null);
  const [modalState, setModalState] = useState({ open: false, orderId: null, section: null, title: "" });
  const [modalScrolled, setModalScrolled] = useState(false);

  const modalScrollRef = useRef(null);
  const scrollStateRef = useRef(null);
  const scrollControllersRef = useRef({});

  const ensureScrollState = useCallback(() => {
    if (scrollStateRef.current) return scrollStateRef.current;
    if (typeof window === "undefined") {
      scrollStateRef.current = {};
      return scrollStateRef.current;
    }
    try {
      const raw = localStorage.getItem(SCROLL_STORAGE_KEY);
      scrollStateRef.current = raw ? JSON.parse(raw) : {};
    } catch (err) {
      console.error("Failed to parse scroll state", err);
      scrollStateRef.current = {};
    }
    return scrollStateRef.current;
  }, []);

  const getScrollValue = useCallback(
    (key) => {
      const state = ensureScrollState();
      return state[key] ?? 0;
    },
    [ensureScrollState]
  );

  const setScrollValue = useCallback(
    (key, value) => {
      const state = ensureScrollState();
      state[key] = value;
      scrollStateRef.current = state;
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(SCROLL_STORAGE_KEY, JSON.stringify(state));
        } catch (err) {
          console.error("Failed to persist scroll state", err);
        }
      }
    },
    [ensureScrollState]
  );

  const registerScrollArea = useCallback((key, handler) => {
    scrollControllersRef.current[key] = handler;
    return () => {
      if (scrollControllersRef.current[key] === handler) {
        delete scrollControllersRef.current[key];
      }
    };
  }, []);

  const load = useCallback(() => {
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
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const handlePay = (id) => {
    axios.post(`${API}/purchase/${id}/pay`).then(load).catch(console.error);
  };
  const handleCancel = (id) => {
    axios.post(`${API}/purchase/${id}/cancel`).then(load).catch(console.error);
  };
  const handleRefund = (id) => {
    axios.post(`${API}/purchase/${id}/refund`).then(load).catch(console.error);
  };

  const handleTicketDownload = async (ticketId) => {
    try {
      await downloadTicketPdf(ticketId);
    } catch (err) {
      console.error("Не удалось скачать билет", err);
      window.alert("Не удалось скачать билет. Попробуйте ещё раз.");
    }
  };

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return items;
    return items.filter((p) => {
      const fields = [p.customer_name, p.customer_phone, p.customer_email];
      return fields.some((field) => field && String(field).toLowerCase().includes(query));
    });
  }, [items, search]);

  useEffect(() => {
    if (expandedId && !filteredItems.some((p) => p.id === expandedId)) {
      setExpandedId(null);
    }
  }, [filteredItems, expandedId]);

  const statusBadge = (s) => {
    const tone = statusToneMap[s] || "neutral";
    return <span className={`purchases-badge purchases-badge--${tone}`}>{s}</span>;
  };

  const formatAmount = (value) => {
    if (value === undefined || value === null) return "—";
    const amountNumber = Number(value);
    if (Number.isNaN(amountNumber)) return String(value);
    return `${amountNumber.toLocaleString("ru-RU", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} €`;
  };

  const toggleInfo = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const openModal = (orderId, section, title) => {
    setModalScrolled(false);
    setModalState({ open: true, orderId, section, title });
  };

  const closeModal = () => {
    if (!modalState.open) return;
    const key = makeScrollKey(modalState.orderId, modalState.section);
    const top = modalScrollRef.current ? Math.round(modalScrollRef.current.scrollTop) : 0;
    setScrollValue(key, top);
    const controller = scrollControllersRef.current[key];
    if (typeof controller === "function") {
      controller(top);
    }
    setModalState({ open: false, orderId: null, section: null, title: "" });
    setModalScrolled(false);
  };

  useEffect(() => {
    if (!modalState.open) return undefined;
    const handler = (e) => {
      if (e.key === "Escape") {
        closeModal();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [modalState.open, closeModal]);

  useEffect(() => {
    if (!modalState.open) return undefined;
    const el = modalScrollRef.current;
    if (!el) return undefined;
    const key = makeScrollKey(modalState.orderId, modalState.section);
    const initial = getScrollValue(key);
    if (initial) {
      el.scrollTop = initial;
    }
    setModalScrolled(el.scrollTop > 24);
    const handleScroll = () => {
      const top = Math.round(el.scrollTop);
      setModalScrolled(top > 24);
      setScrollValue(key, top);
    };
    el.addEventListener("scroll", handleScroll);
    return () => el.removeEventListener("scroll", handleScroll);
  }, [modalState, getScrollValue, setScrollValue]);

  const handleModalToTop = (e) => {
    e.stopPropagation();
    const el = modalScrollRef.current;
    if (!el) return;
    el.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => {
      if (!modalState.open || !modalScrollRef.current) return;
      const top = Math.round(modalScrollRef.current.scrollTop);
      const key = makeScrollKey(modalState.orderId, modalState.section);
      setScrollValue(key, top);
      setModalScrolled(top > 24);
    }, 300);
  };

  const modalPurchaseInfo = modalState.open ? info[modalState.orderId] : null;

  const renderTicketsTable = (purchaseInfo) => {
    const tickets = purchaseInfo?.tickets ?? [];
    return (
      <table className="purchases-subtable">
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
                <td>{t.from_stop_name || "—"}</td>
                <td>{t.to_stop_name || "—"}</td>
                <td>{formatDateShort(t.tour_date)}</td>
                <td>{t.seat_num ?? "—"}</td>
                <td>{t.extra_baggage ? "Да" : "—"}</td>
                <td>
                  <button
                    type="button"
                    className="purchases-btn purchases-btn--small"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleTicketDownload(t.id);
                    }}
                  >
                    Скачать PDF
                  </button>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan="7" className="purchases-empty">
                Нет билетов
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  };

  const renderLogsTable = (purchaseInfo) => {
    const logs = purchaseInfo?.logs ?? [];
    return (
      <table className="purchases-subtable">
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
                <td>{formatDateTime(l.at)}</td>
                <td>{l.by || "—"}</td>
                <td>{l.method || "—"}</td>
                <td>{l.amount ?? "—"}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan="5" className="purchases-empty">
                Нет действий
              </td>
            </tr>
          )}
        </tbody>
      </table>
    );
  };

  const purchaseTripSummary = (purchaseId) => {
    const tickets = info[purchaseId]?.tickets ?? [];
    if (!tickets.length) return null;
    const sorted = [...tickets].sort((a, b) => {
      const left = a.tour_date || "";
      const right = b.tour_date || "";
      return left.localeCompare(right);
    });
    const first = sorted[0];
    const dates = Array.from(new Set(sorted.map((t) => t.tour_date).filter(Boolean))).sort();
    return {
      date: dates[0] ? formatDateShort(dates[0]) : "",
      from: first?.from_stop_name,
      to: first?.to_stop_name,
      ticketsCount: tickets.length,
    };
  };

  const passengersCount = (purchaseId) => {
    const tickets = info[purchaseId]?.tickets ?? [];
    if (!tickets.length) return 0;
    const uniq = new Set();
    tickets.forEach((t) => {
      if (t.passenger_id) {
        uniq.add(`id:${t.passenger_id}`);
      } else if (t.passenger_name) {
        uniq.add(`name:${t.passenger_name}`);
      } else {
        uniq.add(`ticket:${t.id}`);
      }
    });
    return uniq.size;
  };

  return (
    <div className="purchases-page">
      <div className="purchases-page__container">
        <h1>Покупки</h1>
        <div className="purchases-toolbar">
          <label htmlFor="purchases-status">Статус:</label>
          <select
            id="purchases-status"
            className="purchases-select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Все</option>
            <option value="reserved">reserved</option>
            <option value="paid">paid</option>
            <option value="cancelled">cancelled</option>
            <option value="refunded">refunded</option>
          </select>
          <input
            type="search"
            className="purchases-input"
            placeholder="Поиск по клиенту / телефону / email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="button" className="purchases-btn">
            Экспорт
          </button>
        </div>

        <div className="purchases-table-wrap">
          <table className="purchases-table">
            <thead>
              <tr>
                <th className="purchases-cell-id">№</th>
                <th>Клиент</th>
                <th>Поездка</th>
                <th className="purchases-num">Сумма</th>
                <th>Статус</th>
                <th>Оплата</th>
                <th style={{ width: 210 }}>Действия</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((p) => {
                const isExpanded = expandedId === p.id;
                const summary = purchaseTripSummary(p.id);
                const ticketCount = summary?.ticketsCount ?? (info[p.id]?.tickets?.length || 0);
                const passengerTotal = passengersCount(p.id);
                const paymentMethod = p.payment_method || "—";

                return (
                  <React.Fragment key={p.id}>
                    <tr
                      className="purchases-row"
                      data-status={p.status}
                      onClick={(e) => {
                        if (e.target.closest?.(".purchases-actions")) return;
                        toggleInfo(p.id);
                      }}
                    >
                      <td className="purchases-cell-id">{p.id}</td>
                      <td className="purchases-cell-client">
                        <b>{p.customer_name}</b>
                        {p.customer_phone && <small>{p.customer_phone}</small>}
                        {p.customer_email && <small>{p.customer_email}</small>}
                      </td>
                      <td className="purchases-cell-trip">
                        {summary ? (
                          <>
                            <div>
                              <strong>
                                <span className="purchases-mono">{summary.date}</span> · {summary.from || "—"} → {summary.to || "—"}
                              </strong>
                            </div>
                            <small>Пассажиров: {passengerTotal || "—"} · Билетов: {ticketCount || "—"}</small>
                          </>
                        ) : (
                          <small>Нет данных</small>
                        )}
                      </td>
                      <td className="purchases-num">
                        <span className="purchases-cell-sum purchases-mono">{formatAmount(p.amount_due)}</span>
                      </td>
                      <td>{statusBadge(p.status)}</td>
                      <td>{paymentMethod === "—" ? paymentMethod : <span className="purchases-pill">{paymentMethod}</span>}</td>
                      <td>
                        <div className="purchases-actions">
                          <button
                            type="button"
                            className="purchases-btn purchases-btn--cta"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (p.status === "reserved") {
                                handlePay(p.id);
                              } else if (p.status === "paid") {
                                handleRefund(p.id);
                              }
                            }}
                          >
                            {p.status === "reserved" ? "Оплатить" : p.status === "paid" ? "Возврат" : "Действие"}
                          </button>
                          <button
                            type="button"
                            className="purchases-btn purchases-btn--more"
                            aria-expanded={isExpanded}
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleInfo(p.id);
                            }}
                          >
                            ⋯
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && info[p.id] && (
                      <tr className="purchases-expand-row" data-details-for={p.id}>
                        <td colSpan="7">
                          <div className="purchases-panel">
                            <div className="purchases-card" data-section="tickets">
                              <div className="purchases-card__header">
                                <span>Билеты</span>
                                <div className="purchases-card__actions">
                                  <button
                                    type="button"
                                    className="purchases-btn purchases-btn--small"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      openModal(p.id, "tickets", "Билеты");
                                    }}
                                  >
                                    Развернуть
                                  </button>
                                </div>
                              </div>
                              <div className="purchases-card__body">
                                <ScrollArea
                                  orderId={p.id}
                                  section="tickets"
                                  onRegister={registerScrollArea}
                                  getScrollValue={getScrollValue}
                                  setScrollValue={setScrollValue}
                                >
                                  {renderTicketsTable(info[p.id])}
                                </ScrollArea>
                              </div>
                            </div>

                            <div className="purchases-card" data-section="logs">
                              <div className="purchases-card__header">
                                <span>Логи заказа</span>
                                <div className="purchases-card__actions">
                                  <button
                                    type="button"
                                    className="purchases-btn purchases-btn--small"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      openModal(p.id, "logs", "Логи заказа");
                                    }}
                                  >
                                    Развернуть
                                  </button>
                                </div>
                              </div>
                              <div className="purchases-card__body">
                                <ScrollArea
                                  orderId={p.id}
                                  section="logs"
                                  onRegister={registerScrollArea}
                                  getScrollValue={getScrollValue}
                                  setScrollValue={setScrollValue}
                                >
                                  {renderLogsTable(info[p.id])}
                                </ScrollArea>
                              </div>
                            </div>

                            <div className="purchases-card">
                              <div className="purchases-card__header">
                                <span>Действия</span>
                              </div>
                              <div className="purchases-actions-card">
                                <button
                                  type="button"
                                  className="purchases-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleInfo(p.id);
                                  }}
                                >
                                  Скрыть
                                </button>
                                {p.status === "reserved" && (
                                  <>
                                    <button
                                      type="button"
                                      className="purchases-btn purchases-btn--primary"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handlePay(p.id);
                                      }}
                                    >
                                      Отметить оплату (оффлайн)
                                    </button>
                                    <button
                                      type="button"
                                      className="purchases-btn purchases-btn--ghost"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleCancel(p.id);
                                      }}
                                    >
                                      Отменить бронь
                                    </button>
                                  </>
                                )}
                                {p.status === "paid" && (
                                  <button
                                    type="button"
                                    className="purchases-btn purchases-btn--ghost"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleRefund(p.id);
                                    }}
                                  >
                                    Оформить возврат
                                  </button>
                                )}
                              </div>
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
      </div>

      <div
        className={`purchases-modal${modalState.open ? " purchases-modal--open" : ""}`}
        role="dialog"
        aria-modal={modalState.open ? "true" : "false"}
        aria-labelledby="purchases-modal-title"
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            closeModal();
          }
        }}
      >
        {modalState.open && (
          <div className="purchases-modal__sheet">
            <div className="purchases-modal__header">
              <h2 className="purchases-modal__title" id="purchases-modal-title">
                {modalState.title}
              </h2>
              <button type="button" className="purchases-btn" onClick={closeModal}>
                Закрыть
              </button>
            </div>
            <div className="purchases-modal__body">
              <div
                className={`purchases-modal__scroll${modalScrolled ? " purchases-scroll--scrolled" : ""}`}
                ref={modalScrollRef}
              >
                {modalState.section === "tickets" && renderTicketsTable(modalPurchaseInfo)}
                {modalState.section === "logs" && renderLogsTable(modalPurchaseInfo)}
                <button type="button" className="purchases-to-top" onClick={handleModalToTop}>
                  ↑ <span>Вверх</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ScrollArea({ orderId, section, children, onRegister, getScrollValue, setScrollValue }) {
  const scrollRef = useRef(null);
  const [scrolled, setScrolled] = useState(false);
  const storageKey = useMemo(() => makeScrollKey(orderId, section), [orderId, section]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;
    const initial = getScrollValue(storageKey);
    if (initial) {
      el.scrollTop = initial;
    }
    setScrolled(el.scrollTop > 24);
    const handleScroll = () => {
      const top = Math.round(el.scrollTop);
      setScrolled(top > 24);
      setScrollValue(storageKey, top);
    };
    el.addEventListener("scroll", handleScroll);
    const unregister = onRegister(storageKey, (value) => {
      if (!scrollRef.current) return;
      scrollRef.current.scrollTop = value;
      setScrolled(value > 24);
    });
    return () => {
      el.removeEventListener("scroll", handleScroll);
      unregister();
    };
  }, [storageKey, onRegister, getScrollValue, setScrollValue]);

  const handleToTop = (e) => {
    e.stopPropagation();
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => {
      if (!scrollRef.current) return;
      const top = Math.round(scrollRef.current.scrollTop);
      setScrollValue(storageKey, top);
      setScrolled(top > 24);
    }, 300);
  };

  return (
    <div className={`purchases-scroll${scrolled ? " purchases-scroll--scrolled" : ""}`} ref={scrollRef}>
      {children}
      <button type="button" className="purchases-to-top" onClick={handleToTop}>
        ↑ <span>Вверх</span>
      </button>
    </div>
  );
}
