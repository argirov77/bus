// src/pages/SearchPage.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import SeatClient from "../components/SeatClient";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import Calendar from "../components/Calendar";

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

  const [seatCount, setSeatCount] = useState(1);
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [passengerNames, setPassengerNames] = useState([""]);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [extraBaggage, setExtraBaggage] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("info");
  const [loading, setLoading] = useState(false);
  const [purchaseId, setPurchaseId] = useState(null);

  useEffect(() => {
    setPassengerNames(Array(seatCount).fill(""));
    setSelectedSeats([]);
    setSelectedDate("");
    setSelectedTour(null);
  }, [seatCount]);

  // 1. Загрузить все отправные остановки
  useEffect(() => {
    axios.get(`${API}/search/departures`, { params: { seats: seatCount } })
      .then(res => setDepartureStops(res.data))
      .catch(console.error);
  }, [seatCount]);

  // 2. При выборе отправной — подгрузить конечные
  useEffect(() => {
    if (!selectedDeparture) {
      setArrivalStops([]);
      setTours([]);
      setSelectedTour(null);
    } else {
      axios.get(`${API}/search/arrivals`, {
        params: { departure_stop_id: selectedDeparture, seats: seatCount }
      })
      .then(res => setArrivalStops(res.data))
      .catch(console.error);
    }
  }, [selectedDeparture, seatCount]);

  // 3. При выборе отправной+конечной — подгрузить доступные даты
  useEffect(() => {
    if (!selectedDeparture || !selectedArrival) {
      setDates([]);
      setTours([]);
      setSelectedTour(null);
      setSelectedDate("");
    } else {
      axios.get(`${API}/search/dates`, {
        params: {
          departure_stop_id: selectedDeparture,
          arrival_stop_id:   selectedArrival,
          seats:             seatCount
        }
      })
      .then(res => setDates(res.data))
      .catch(console.error);
    }
  }, [selectedDeparture, selectedArrival, seatCount]);

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
        date:              selectedDate,
        seats:             seatCount
      }
    })
    .then(res => {
      setTours(res.data);
      setSelectedTour(null);
      setSelectedSeats([]);
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
    setSelectedSeats([]);
    setMessage("");
  };

  // 6. Сабмит формы бронирования
  const handleAction = (action) => {
    if (!selectedTour) {
      setMessage("Сначала выберите рейс");
      setMessageType("error");
      return;
    }
    if (selectedSeats.length !== seatCount) {
      setMessage("Выберите нужное количество мест");
      setMessageType("error");
      return;
    }
    if (passengerNames.some(n => !n)) {
      setMessage("Заполните имена пассажиров");
      setMessageType("error");
      return;
    }
    if (!phone || !email) {
      setMessage("Заполните контактные данные");
      setMessageType("error");
      return;
    }
    setMessage(action === 'purchase' ? "Покупка…" : "Бронирование…");
    setMessageType("info");
    setLoading(true);
    axios.post(`${API}/${action === 'purchase' ? 'purchase' : 'book'}`, {
      tour_id:            selectedTour.id,
      seat_nums:          selectedSeats,
      passenger_names:    passengerNames,
      passenger_phone:    phone,
      passenger_email:    email,
      departure_stop_id:  Number(selectedDeparture),
      arrival_stop_id:    Number(selectedArrival),
      extra_baggage:      extraBaggage
    })
    .then(res => {
      const msg = action === 'purchase'
        ? `Билет куплен! Purchase ID: ${res.data.purchase_id}`
        : `Билет забронирован! Purchase ID: ${res.data.purchase_id}`;
      setPurchaseId(res.data.purchase_id);
      setMessage(msg);
      setMessageType("success");
      // сброс полей и перезагрузка схемы мест
      setSelectedSeats([]);
      setPassengerNames(Array(seatCount).fill(""));
      setPhone("");
      setEmail("");
      setExtraBaggage(false);
    })
    .catch(err => {
      console.error(err);
      setMessage(action === 'purchase' ? "Ошибка при покупке" : "Ошибка при бронировании");
      setMessageType("error");
    })
    .finally(() => setLoading(false));
  };

  const handlePay = () => {
    if (!purchaseId) {
      setMessage("Нет бронирования для оплаты");
      setMessageType("error");
      return;
    }
    setMessage("Оплата…");
    setMessageType("info");
    setLoading(true);
    axios.post(`${API}/pay`, { purchase_id: purchaseId })
      .then(() => {
        setMessage("Бронирование оплачено!");
        setMessageType("success");
        setPurchaseId(null);
      })
      .catch(err => {
        console.error(err);
        setMessage("Ошибка при оплате");
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

      <input
        type="number"
        min="1"
        value={seatCount}
        onChange={e => setSeatCount(Number(e.target.value))}
        style={{ width: 60 }}
      />

      <button type="submit">Найти</button>
    </form>

    {dates.length > 0 && (
      <div style={{ marginBottom: 20 }}>
        <Calendar
          activeDates={dates}
          selectedDate={selectedDate}
          onSelect={setSelectedDate}
        />
      </div>
    )}

    {selectedDate && <p>Выбранная дата: {selectedDate}</p>}

    {loading && <Loader />}

    <Alert type={messageType} message={message} />

    {tours.length > 0 && (
      <>
        <h3>Найденные рейсы:</h3>
        {tours.map(t => (
          <div key={t.id} style={{ display:'flex', marginBottom:8 }}>
            <span>Рейс #{t.id}, дата: {t.date}</span>
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
            selectedSeats={selectedSeats}
            maxSeats={seatCount}
            onChange={setSelectedSeats}
          />

          {selectedSeats.length > 0 && (
            <p>Вы выбрали места: {selectedSeats.join(", ")}</p>
          )}

          <form onSubmit={e => e.preventDefault()}
                style={{ marginTop:20, display:"flex", flexDirection:"column", gap:8, maxWidth:300 }}>
            {passengerNames.map((name, idx) => (
              <input
                key={idx}
                type="text"
                placeholder={`Имя пассажира ${idx + 1}`}
                required
                value={name}
                onChange={e => {
                  const arr = [...passengerNames];
                  arr[idx] = e.target.value;
                  setPassengerNames(arr);
                }}
              />
            ))}
            <input
              type="tel"
              placeholder="Телефон"
              required
              value={phone}
              onChange={e => setPhone(e.target.value)}
            />
            <input
              type="email"
              placeholder="Email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
            <label style={{display:'flex',alignItems:'center',gap:4}}>
              <input
                type="checkbox"
                checked={extraBaggage}
                onChange={e => setExtraBaggage(e.target.checked)}
              />
              Дополнительный багаж
            </label>
            <div style={{display:'flex', gap:8}}>
              <button type="button" onClick={() => handleAction('book')}>Бронь</button>
              <button type="button" onClick={() => handleAction('purchase')}>Покупка</button>
              {purchaseId && (
                <button type="button" onClick={handlePay}>Оплатить</button>
              )}
            </div>
          </form>
        </>
      )}
    </div>
  );
}
