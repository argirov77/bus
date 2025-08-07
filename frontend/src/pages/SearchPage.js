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
  const [departDates, setDepartDates]       = useState([]);
  const [returnDates, setReturnDates]       = useState([]);

  const [selectedDeparture, setSelectedDeparture] = useState("");
  const [selectedArrival, setSelectedArrival]     = useState("");
  const [selectedDepartDate, setSelectedDepartDate] = useState("");
  const [selectedReturnDate, setSelectedReturnDate] = useState("");
  const [showDepartCal, setShowDepartCal] = useState(false);
  const [showReturnCal, setShowReturnCal] = useState(false);

  const [outboundTours, setOutboundTours] = useState([]);
  const [returnTours, setReturnTours] = useState([]);
  const [selectedOutboundTour, setSelectedOutboundTour] = useState(null);
  const [selectedReturnTour, setSelectedReturnTour] = useState(null);

  const [seatCount, setSeatCount] = useState(1);
  const [selectedOutboundSeats, setSelectedOutboundSeats] = useState([]);
  const [selectedReturnSeats, setSelectedReturnSeats] = useState([]);
  const [passengerNames, setPassengerNames] = useState([""]);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [extraBaggageOutbound, setExtraBaggageOutbound] = useState([false]);
  const [extraBaggageReturn, setExtraBaggageReturn] = useState([false]);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("info");
  const [loading, setLoading] = useState(false);
  const [purchaseId, setPurchaseId] = useState(null);

  const today = new Date().toISOString().slice(0, 10);
  const returnMinDate = selectedDepartDate
    ? new Date(new Date(selectedDepartDate).getTime() + 86400000).toISOString().slice(0, 10)
    : today;

  useEffect(() => {
    setPassengerNames(Array(seatCount).fill(""));
    setSelectedOutboundSeats([]);
    setSelectedReturnSeats([]);
    setSelectedDepartDate("");
    setSelectedReturnDate("");
    setSelectedOutboundTour(null);
    setSelectedReturnTour(null);
    setExtraBaggageOutbound(Array(seatCount).fill(false));
    setExtraBaggageReturn(Array(seatCount).fill(false));
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
      setOutboundTours([]);
      setReturnTours([]);
      setSelectedOutboundTour(null);
      setSelectedReturnTour(null);
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
      setDepartDates([]);
      setReturnDates([]);
      setOutboundTours([]);
      setReturnTours([]);
      setSelectedOutboundTour(null);
      setSelectedReturnTour(null);
      setSelectedDepartDate("");
      setSelectedReturnDate("");
    } else {
      axios.get(`${API}/search/dates`, {
        params: {
          departure_stop_id: selectedDeparture,
          arrival_stop_id:   selectedArrival,
          seats:             seatCount
        }
      })
      .then(res => setDepartDates(res.data))
      .catch(console.error);

      axios.get(`${API}/search/dates`, {
        params: {
          departure_stop_id: selectedArrival,
          arrival_stop_id:   selectedDeparture,
          seats:             seatCount
        }
      })
      .then(res => setReturnDates(res.data))
      .catch(console.error);
    }
  }, [selectedDeparture, selectedArrival, seatCount]);

  // 4. Поиск рейсов на выбранные даты
  const handleSearchTours = async e => {
    e.preventDefault();
    if (!selectedDeparture || !selectedArrival || !selectedDepartDate) {
      setMessage("Заполните все поля поиска");
      setMessageType("error");
      return;
    }
    setMessage("Идёт поиск…");
    setMessageType("info");
    setLoading(true);
    try {
      const outReq = axios.get(`${API}/tours/search`, {
        params: {
          departure_stop_id: selectedDeparture,
          arrival_stop_id:   selectedArrival,
          date:              selectedDepartDate,
          seats:             seatCount
        }
      });
      const retReq = selectedReturnDate
        ? axios.get(`${API}/tours/search`, {
            params: {
              departure_stop_id: selectedArrival,
              arrival_stop_id:   selectedDeparture,
              date:              selectedReturnDate,
              seats:             seatCount
            }
          })
        : Promise.resolve({ data: [] });
      const [outRes, retRes] = await Promise.all([outReq, retReq]);
      setOutboundTours(outRes.data);
      setReturnTours(retRes.data);
      setSelectedOutboundTour(null);
      setSelectedReturnTour(null);
      setSelectedOutboundSeats([]);
      setSelectedReturnSeats([]);
      if (!outRes.data.length && (!selectedReturnDate || !retRes.data.length)) {
        setMessage("Рейсы не найдены");
        setMessageType("info");
      } else {
        setMessage("");
      }
    } catch (err) {
      console.error(err);
      setMessage("Ошибка поиска рейсов");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  };

  // 5. Выбор рейсов туда и обратно
  const handleOutboundTourSelect = tour => {
    setSelectedOutboundTour(tour);
    setSelectedOutboundSeats([]);
    setSelectedReturnSeats([]);
    setMessage("");
  };

  const handleReturnTourSelect = tour => {
    setSelectedReturnTour(tour);
    setSelectedOutboundSeats([]);
    setSelectedReturnSeats([]);
    setMessage("");
  };

  // 6. Сабмит формы бронирования
  const handleAction = async (action) => {
    if (!selectedOutboundTour || (selectedReturnDate && !selectedReturnTour)) {
      setMessage("Сначала выберите рейсы");
      setMessageType("error");
      return;
    }
    if (
      selectedOutboundSeats.length !== seatCount ||
      (selectedReturnTour && selectedReturnSeats.length !== seatCount)
    ) {
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
    try {
      const endpoint = action === 'purchase' ? 'purchase' : 'book';
      const basePayload = {
        passenger_names: passengerNames,
        passenger_phone: phone,
        passenger_email: email
      };
      const outRes = await axios.post(`${API}/${endpoint}`, {
        ...basePayload,
        seat_nums:       selectedOutboundSeats,
        extra_baggage:   extraBaggageOutbound,
        tour_id:         selectedOutboundTour.id,
        departure_stop_id: Number(selectedDeparture),
        arrival_stop_id:   Number(selectedArrival)
      });
      let total = outRes.data.amount_due;
      let ids = [outRes.data.purchase_id];
      if (selectedReturnTour) {
        const retRes = await axios.post(`${API}/${endpoint}`, {
          ...basePayload,
          seat_nums:       selectedReturnSeats,
          extra_baggage:   extraBaggageReturn,
          tour_id:         selectedReturnTour.id,
          departure_stop_id: Number(selectedArrival),
          arrival_stop_id:   Number(selectedDeparture)
        });
        total += retRes.data.amount_due;
        ids.push(retRes.data.purchase_id);
      }
      const msg = action === 'purchase'
        ? `Билеты куплены! Purchase ID: ${ids.join(', ')}. Сумма: ${total.toFixed(2)}`
        : `Билеты забронированы! Purchase ID: ${ids.join(', ')}. Сумма: ${total.toFixed(2)}`;
      setPurchaseId(ids[ids.length - 1]);
      setMessage(msg);
      setMessageType("success");
      setSelectedOutboundSeats([]);
      setSelectedReturnSeats([]);
      setPassengerNames(Array(seatCount).fill(""));
      setPhone("");
      setEmail("");
      setExtraBaggageOutbound(Array(seatCount).fill(false));
      setExtraBaggageReturn(Array(seatCount).fill(false));
    } catch (err) {
      console.error(err);
      setMessage(action === 'purchase' ? "Ошибка при покупке" : "Ошибка при бронировании");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
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
      <form onSubmit={handleSearchTours} style={{ display:"flex", gap:8, marginBottom:20, flexWrap:'wrap' }}>
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

        <input
          type="text"
          readOnly
          placeholder="Дата туда"
          value={selectedDepartDate}
          onClick={() => { setShowDepartCal(v => !v); setShowReturnCal(false); }}
        />

        <input
          type="text"
          readOnly
          placeholder="Дата обратно"
          value={selectedReturnDate}
          onClick={() => {
            if (returnDates.length) {
              setShowReturnCal(v => !v);
              setShowDepartCal(false);
            }
          }}
          disabled={!returnDates.length}
        />

        <button type="submit">Найти</button>
      </form>

      {showDepartCal && (
        <div style={{ marginBottom: 20 }}>
          <Calendar
            activeDates={departDates}
            selectedDate={selectedDepartDate}
            minDate={today}
            onSelect={d => {
              setSelectedDepartDate(d);
              setShowDepartCal(false);
              if (selectedReturnDate && selectedReturnDate <= d) {
                setSelectedReturnDate('');
              }
            }}
          />
        </div>
      )}

      {showReturnCal && (
        <div style={{ marginBottom: 20 }}>
          <Calendar
            activeDates={returnDates}
            selectedDate={selectedReturnDate}
            minDate={returnMinDate}
            onSelect={d => { setSelectedReturnDate(d); setShowReturnCal(false); }}
          />
        </div>
      )}

      {selectedDepartDate && <p>Выбранная дата туда: {selectedDepartDate}</p>}
      {selectedReturnDate && <p>Выбранная дата обратно: {selectedReturnDate}</p>}

    {loading && <Loader />}

    <Alert type={messageType} message={message} />

    {outboundTours.length > 0 && (
      <>
        <h3>Рейсы туда:</h3>
        {outboundTours.map(t => (
          <div key={t.id} style={{ display:'flex', marginBottom:8 }}>
            <span>Рейс #{t.id}, дата: {t.date}</span>
            <button style={{ marginLeft:8 }} onClick={() => handleOutboundTourSelect(t)}>
              Выбрать
            </button>
          </div>
        ))}
      </>
    )}

    {selectedReturnDate && returnTours.length > 0 && (
      <>
        <h3>Рейсы обратно:</h3>
        {returnTours.map(t => (
          <div key={t.id} style={{ display:'flex', marginBottom:8 }}>
            <span>Рейс #{t.id}, дата: {t.date}</span>
            <button style={{ marginLeft:8 }} onClick={() => handleReturnTourSelect(t)}>
              Выбрать
            </button>
          </div>
        ))}
      </>
    )}

    {selectedOutboundTour && (!selectedReturnDate || selectedReturnTour) && (
      <>
        <h3>Рейс туда #{selectedOutboundTour.id}, дата: {selectedOutboundTour.date}</h3>
        <p>Свободно мест: {selectedOutboundTour.seats}</p>
        <p>Выберите место:</p>

        <SeatClient
          tourId={selectedOutboundTour.id}
          departureStopId={selectedDeparture}
          arrivalStopId={selectedArrival}
          layoutVariant={selectedOutboundTour.layout_variant}
          selectedSeats={selectedOutboundSeats}
          maxSeats={seatCount}
          onChange={setSelectedOutboundSeats}
        />

        {selectedOutboundSeats.length > 0 && (
          <p>Вы выбрали места: {selectedOutboundSeats.join(", ")}</p>
        )}

        {selectedReturnTour && (
          <>
            <h3>Рейс обратно #{selectedReturnTour.id}, дата: {selectedReturnTour.date}</h3>
            <p>Свободно мест: {selectedReturnTour.seats}</p>
            <p>Выберите место:</p>
            <SeatClient
              tourId={selectedReturnTour.id}
              departureStopId={selectedArrival}
              arrivalStopId={selectedDeparture}
              layoutVariant={selectedReturnTour.layout_variant}
              selectedSeats={selectedReturnSeats}
              maxSeats={seatCount}
              onChange={setSelectedReturnSeats}
            />
            {selectedReturnSeats.length > 0 && (
              <p>Вы выбрали места обратно: {selectedReturnSeats.join(", ")}</p>
            )}
          </>
        )}

        <form onSubmit={e => e.preventDefault()}
              style={{ marginTop:20, display:"flex", flexDirection:"column", gap:8, maxWidth:300 }}>
          {passengerNames.map((name, idx) => (
            <div key={idx} style={{display:'flex',alignItems:'center',gap:4}}>
              <input
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
              <label style={{display:'flex',alignItems:'center',gap:2}}>
                <input
                  type="checkbox"
                  checked={extraBaggageOutbound[idx]}
                  onChange={e => {
                    const arr = [...extraBaggageOutbound];
                    arr[idx] = e.target.checked;
                    setExtraBaggageOutbound(arr);
                  }}
                />
                Багаж туда
              </label>
              {selectedReturnTour && (
                <label style={{display:'flex',alignItems:'center',gap:2}}>
                  <input
                    type="checkbox"
                    checked={extraBaggageReturn[idx]}
                    onChange={e => {
                      const arr = [...extraBaggageReturn];
                      arr[idx] = e.target.checked;
                      setExtraBaggageReturn(arr);
                    }}
                  />
                  Багаж обратно
                </label>
              )}
            </div>
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
