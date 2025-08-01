// src/pages/SearchPage.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import SeatClient from "../components/SeatClient";
import Loader from "../components/Loader";
import Alert from "../components/Alert";

import { API } from "../config";

export default function SearchPage() {
  const [departureStops, setDepartureStops] = useState([]);
  const [arrivalStops, setArrivalStops]     = useState([]);
  const [dates, setDates]                   = useState([]);

  const [selectedDeparture, setSelectedDeparture] = useState("");
  const [selectedArrival, setSelectedArrival]     = useState("");
  const [selectedDate, setSelectedDate]           = useState("");

  const [tours, setTours]               = useState([]);
  const [selectedTour, setSelectedTour] = useState(null);

  const [selectedSeat, setSelectedSeat] = useState(null);

  const [passengerData, setPassengerData] = useState({
    name: "", phone: "", email: ""
  });
  const [extraBaggage, setExtraBaggage] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("info");
  const [loading, setLoading] = useState(false);

  // 1. Загрузить все отправные остановки
  useEffect(() => {
    axios.get(`${API}/search/departures`)
      .then(res => setDepartureStops(res.data))
      .catch(console.error);
  }, []);

  // 2. При выборе отправной — подгрузить конечные
  useEffect(() => {
    if (!selectedDeparture) {
      setArrivalStops([]);
      setTours([]);
      setSelectedTour(null);
    } else {
      axios.get(`${API}/search/arrivals`, {
        params: { departure_stop_id: selectedDeparture }
      })
      .then(res => setArrivalStops(res.data))
      .catch(console.error);
    }
  }, [selectedDeparture]);

  // 3. При выборе отправной+конечной — подгрузить доступные даты
  useEffect(() => {
    if (!selectedDeparture || !selectedArrival) {
      setDates([]);
      setTours([]);
      setSelectedTour(null);
    } else {
      axios.get(`${API}/search/dates`, {
        params: {
          departure_stop_id: selectedDeparture,
          arrival_stop_id:   selectedArrival
        }
      })
      .then(res => setDates(res.data))
      .catch(console.error);
    }
  }, [selectedDeparture, selectedArrival]);

  // 4. Поиск рейсов на выбранную дату
  const handleSearchTours = e => {
    e.preventDefault();
    if (!selectedDeparture || !selectedArrival || !selectedDate) {
      setMessage("Заполните все поля поиска");
      setMessageType("error");
      return;
    }
    setMessage("Идёт поиск…");
    setMessageType("info");
    setLoading(true);
    axios.get(`${API}/tours/search`, {
      params: {
        departure_stop_id: selectedDeparture,
        arrival_stop_id:   selectedArrival,
        date:              selectedDate
      }
    })
    .then(res => {
      setTours(res.data);
      setSelectedTour(null);
      setSelectedSeat(null);
      if (res.data.length) {
        setMessage("");
      } else {
        setMessage("Рейсы не найдены");
        setMessageType("info");
      }
    })
    .catch(err => {
      console.error(err);
      setMessage("Ошибка поиска рейсов");
      setMessageType("error");
    })
    .finally(() => setLoading(false));
  };

  // 5. Выбрать конкретный рейс
  const handleTourSelect = tour => {
    setSelectedTour(tour);
    setSelectedSeat(null);
    setMessage("");
  };

  // 6. Сабмит формы бронирования
  const handleBooking = e => {
    e.preventDefault();
    if (!selectedTour) {
      setMessage("Сначала выберите рейс");
      setMessageType("error");
      return;
    }
    if (!selectedSeat) {
      setMessage("Сначала выберите место");
      setMessageType("error");
      return;
    }
    setMessage("Бронирование…");
    setMessageType("info");
    setLoading(true);
    axios.post(`${API}/tickets`, {
      tour_id:            selectedTour.id,
      seat_num:           selectedSeat,
      passenger_name:     passengerData.name,
      passenger_phone:    passengerData.phone,
      passenger_email:    passengerData.email,
      departure_stop_id:  Number(selectedDeparture),
      arrival_stop_id:    Number(selectedArrival),
      extra_baggage:      extraBaggage
    })
    .then(res => {
      setMessage(`Билет забронирован! Ticket ID: ${res.data.ticket_id}`);
      setMessageType("success");
      // сброс полей и перезагрузка схемы мест
      setSelectedSeat(null);
      setPassengerData({ name:"", phone:"", email:"" });
      setExtraBaggage(false);
    })
    .catch(err => {
      console.error(err);
      setMessage("Ошибка при бронировании");
      setMessageType("error");
    })
    .finally(() => setLoading(false));
  };

  return (
    <div className="container" style={{ padding: 20 }}>
      <h2>Поиск рейсов</h2>
      <form onSubmit={handleSearchTours} style={{ display:"flex", gap:8, marginBottom:20 }}>
        <select
          value={selectedDeparture}
          onChange={e => setSelectedDeparture(e.target.value)}
        >
          <option value="">Откуда</option>
          {departureStops.map(s => (
            <option key={s.id} value={s.id}>{s.stop_name}</option>
          ))}
        </select>

        <select
          value={selectedArrival}
          onChange={e => setSelectedArrival(e.target.value)}
          disabled={!selectedDeparture}
        >
          <option value="">Куда</option>
          {arrivalStops.map(s => (
            <option key={s.id} value={s.id}>{s.stop_name}</option>
          ))}
        </select>

        <select
          value={selectedDate}
          onChange={e => setSelectedDate(e.target.value)}
          disabled={!selectedArrival}
        >
          <option value="">Дата</option>
          {dates.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <button type="submit">Найти рейсы</button>
      </form>

      {loading && <Loader />}
      {message && <Alert type={messageType} message={message} />}

      {!selectedTour && tours.length > 0 && (
        <>
          <h3>Доступные рейсы</h3>
          {tours.map(t => (
            <div key={t.id} style={{ marginBottom:10 }}>
              <strong>Рейс #{t.id}</strong>, дата: {t.date}, свободно: {t.seats}
              <button style={{ marginLeft:8 }} onClick={() => handleTourSelect(t)}>
                Выбрать
              </button>
            </div>
          ))}
        </>
      )}

      {selectedTour && (
        <>
          <h3>Рейс #{selectedTour.id}, дата: {selectedTour.date}</h3>
          <p>Свободно мест: {selectedTour.seats}</p>
          <p>Выберите место:</p>

          {/* здесь рендерим клиентскую обёртку SeatClient */}
          <SeatClient
            tourId={selectedTour.id}
            departureStopId={selectedDeparture}
            arrivalStopId={selectedArrival}
            layoutVariant={selectedTour.layout_variant}
            onSelect={num => setSelectedSeat(num)}
          />

          {selectedSeat && <p>Вы выбрали место: {selectedSeat}</p>}

          <form onSubmit={handleBooking}
                style={{ marginTop:20, display:"flex", flexDirection:"column", gap:8, maxWidth:300 }}>
            <input
              type="text"
              placeholder="Имя"
              required
              value={passengerData.name}
              onChange={e => setPassengerData({ ...passengerData, name: e.target.value })}
            />
            <input
              type="tel"
              placeholder="Телефон"
              value={passengerData.phone}
              onChange={e => setPassengerData({ ...passengerData, phone: e.target.value })}
            />
            <input
              type="email"
              placeholder="Email"
              value={passengerData.email}
              onChange={e => setPassengerData({ ...passengerData, email: e.target.value })}
            />
            <label style={{display:'flex',alignItems:'center',gap:4}}>
              <input
                type="checkbox"
                checked={extraBaggage}
                onChange={e => setExtraBaggage(e.target.checked)}
              />
              Дополнительный багаж
            </label>
            <button type="submit">Забронировать</button>
          </form>
        </>
      )}
    </div>
  );
}
