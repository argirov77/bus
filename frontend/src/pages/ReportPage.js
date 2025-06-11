import React, { useState, useEffect } from "react";
import axios from "axios";
import "../styles/ReportPage.css";

import { API } from "../config";

function ReportPage() {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [routeId, setRouteId] = useState("");
  const [tourId, setTourId] = useState("");
  const [departureStop, setDepartureStop] = useState("");
  const [arrivalStop, setArrivalStop] = useState("");

  // Списки
  const [routes, setRoutes] = useState([]);
  const [tours, setTours] = useState([]);
  const [stops, setStops] = useState([]);

  // Результат отчёта
  const [reportData, setReportData] = useState(null);
  const [message, setMessage] = useState("");

  // Загружаем маршруты
  useEffect(() => {
    axios.get(`${API}/routes`)
      .then(res => setRoutes(res.data))
      .catch(err => console.error("Ошибка загрузки маршрутов:", err));
  }, []);

  // Загружаем рейсы по маршруту
  useEffect(() => {
    if (routeId) {
      axios.get(`${API}/tours?route_id=${routeId}`)
        .then(res => setTours(res.data))
        .catch(err => console.error("Ошибка загрузки рейсов:", err));
    } else {
      setTours([]);
      setTourId("");
    }
  }, [routeId]);

  // Загружаем все остановки
  useEffect(() => {
    axios.get(`${API}/stops`)
      .then(res => setStops(res.data))
      .catch(err => console.error("Ошибка загрузки остановок:", err));
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    setMessage("Загрузка отчёта...");

    // На бэкенд отправляем ID остановок
    const departureStopId = departureStop || null;
    const arrivalStopId = arrivalStop || null;

    axios.post(`${API}/report/`, {
      start_date: startDate || null,
      end_date: endDate || null,
      route_id: routeId || null,
      tour_id: tourId || null,
      departure_stop_id: departureStopId,
      arrival_stop_id: arrivalStopId
    })
    .then(res => {
      setReportData(res.data);
      setMessage("");
    })
    .catch(err => {
      console.error("Ошибка получения отчёта:", err);
      setMessage("Ошибка получения отчёта");
    });
  };

  return (
    <div className="container report-container">
      <h2>Отчёт по проданным билетам</h2>
      <form onSubmit={handleSearch} className="report-form">
        <div>
          <label>Начальная дата:</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div>
          <label>Конечная дата:</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>

        <div>
          <label>Маршрут:</label>
          <select
            value={routeId}
            onChange={(e) => setRouteId(e.target.value)}
          >
            <option value="">Все маршруты</option>
            {routes.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label>Рейс:</label>
          <select
            value={tourId}
            onChange={(e) => setTourId(e.target.value)}
            disabled={!routeId}
          >
            <option value="">Все рейсы</option>
            {tours.map((t) => (
              <option key={t.id} value={t.id}>
                Рейс #{t.id} - {t.date}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label>Отправная остановка:</label>
          <select
            value={departureStop}
            onChange={(e) => setDepartureStop(e.target.value)}
          >
            <option value="">Все</option>
            {stops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.stop_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label>Конечная остановка:</label>
          <select
            value={arrivalStop}
            onChange={(e) => setArrivalStop(e.target.value)}
          >
            <option value="">Все</option>
            {stops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.stop_name}
              </option>
            ))}
          </select>
        </div>

        <button type="submit">Найти отчёт</button>
      </form>

      {message && <p className="report-message">{message}</p>}

      {reportData && (
        <div className="report-results">
          <h3>Сводка</h3>
          <p>Общее количество билетов: <strong>{reportData.summary.total_tickets}</strong></p>
          <p>Общая сумма продаж: <strong>{reportData.summary.total_sales}</strong></p>

          <h3>Детали билетов</h3>
          {reportData.tickets.length > 0 ? (
            <table className="report-table">
              <thead>
                <tr>
                  <th>Билет</th>
                  <th>Рейс</th>
                  <th>Маршрут</th>
                  <th>Место</th>
                  <th>Цена</th>
                  <th>Пассажир</th>
                  <th>Дата рейса</th>
                  <th>Отправная</th>
                  <th>Конечная</th>
                </tr>
              </thead>
              <tbody>
                {reportData.tickets.map((tk) => (
                  <tr key={tk.ticket_id}>
                    <td>{tk.ticket_id}</td>
                    <td>{tk.tour_id}</td>
                    <td>{tk.route_name}</td>
                    <td>{tk.seat_num}</td>
                    <td>{tk.price}</td>
                    <td>{tk.passenger_name}</td>
                    <td>{tk.tour_date}</td>
                    <td>{tk.departure_stop_name}</td>
                    <td>{tk.arrival_stop_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>Нет проданных билетов по заданным параметрам.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default ReportPage;
