// src/pages/SearchPage.js

import React, { useState, useEffect } from "react";
import axios from "axios";

import SeatClient from "../components/SeatClient";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import Calendar from "../components/Calendar";
import PassengerSelector from "../components/PassengerSelector";

import { API } from "../config";

export default function SearchPage() {
  const supportedLangs = ["ru", "en", "bg", "ua"];
  const browserLang =
    typeof navigator !== "undefined" && navigator.language
      ? navigator.language.slice(0, 2).toLowerCase()
      : "ru";
  const lang = supportedLangs.includes(browserLang) ? browserLang : "ru";
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

  const [adultCount, setAdultCount] = useState(1);
  const [discountCount, setDiscountCount] = useState(0);
  const seatCount = adultCount + discountCount;
  const [selectedOutboundSeats, setSelectedOutboundSeats] = useState([]);
  const [selectedReturnSeats, setSelectedReturnSeats] = useState([]);
  const [passengerNames, setPassengerNames] = useState(Array(seatCount).fill(""));
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
    setSelectedOutboundSeats([]);
    setSelectedReturnSeats([]);
    setSelectedDepartDate("");
    setSelectedReturnDate("");
    setSelectedOutboundTour(null);
    setSelectedReturnTour(null);
    setPassengerNames(Array(seatCount).fill(""));
    setExtraBaggageOutbound(Array(seatCount).fill(false));
    setExtraBaggageReturn(Array(seatCount).fill(false));
  }, [seatCount]);

  // 1. Загрузить все отправные остановки
  useEffect(() => {
    axios.post(`${API}/search/departures`, { seats: seatCount, lang })
      .then(res => setDepartureStops(res.data))
      .catch(console.error);
  }, [seatCount, lang]);

  // 2. При выборе отправной — подгрузить конечные
  useEffect(() => {
    if (!selectedDeparture) {
      setArrivalStops([]);
      setOutboundTours([]);
      setReturnTours([]);
      setSelectedOutboundTour(null);
      setSelectedReturnTour(null);
    } else {
      axios.post(`${API}/search/arrivals`, {
        departure_stop_id: selectedDeparture,
        seats: seatCount,
        lang
      })
      .then(res => setArrivalStops(res.data))
      .catch(console.error);
    }
  }, [selectedDeparture, seatCount, lang]);

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
    const trimmedNames = passengerNames.map(name => name.trim());
    if (
      selectedOutboundSeats.length !== seatCount ||
      (selectedReturnTour && selectedReturnSeats.length !== seatCount)
    ) {
      setMessage("Выберите нужное количество мест");
      setMessageType("error");
      return;
    }
    if (trimmedNames.some(name => !name)) {
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
        passenger_phone: phone,
        passenger_email: email,
        passenger_names: trimmedNames,
        adult_count: adultCount,
        discount_count: discountCount
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
      let pId = outRes.data.purchase_id;
      if (selectedReturnTour) {
        const retRes = await axios.post(`${API}/${endpoint}`, {
          ...basePayload,
          seat_nums:       selectedReturnSeats,
          extra_baggage:   extraBaggageReturn,
          tour_id:         selectedReturnTour.id,
          departure_stop_id: Number(selectedArrival),
          arrival_stop_id:   Number(selectedDeparture),
          purchase_id:     pId
        });
        total = retRes.data.amount_due;
        pId = retRes.data.purchase_id;
      }
      const msg = action === 'purchase'
        ? `Билеты куплены! Purchase ID: ${pId}. Сумма: ${total.toFixed(2)}`
        : `Билеты забронированы! Purchase ID: ${pId}. Сумма: ${total.toFixed(2)}`;
      setPurchaseId(pId);
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

  const handleCancel = () => {
    if (!purchaseId) {
      setMessage("Нет бронирования для отмены");
      setMessageType("error");
      return;
    }
    setMessage("Отмена…");
    setMessageType("info");
    setLoading(true);
    axios.post(`${API}/cancel/${purchaseId}`)
      .then(() => {
        setMessage("Бронирование отменено!");
        setMessageType("success");
        setPurchaseId(null);
      })
      .catch(err => {
        console.error(err);
        setMessage("Ошибка при отмене");
        setMessageType("error");
      })
      .finally(() => setLoading(false));
  };
  const depStopName = departureStops.find(s => s.id === Number(selectedDeparture))?.stop_name || "";
  const arrStopName = arrivalStops.find(s => s.id === Number(selectedArrival))?.stop_name || "";

  const formatDate = d => {
    const [y, m, day] = d.split("-");
    return `${day}/${m}/${y}`;
  };

  const getDuration = (start, end) => {
    const [sh, sm] = start.split(":").map(Number);
    const [eh, em] = end.split(":").map(Number);
    const mins = eh * 60 + em - (sh * 60 + sm);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `${h}ч ${m}м`;
  };

  const calcPrice = price => {
    const adultSum = price * adultCount;
    const discountSum = price * discountCount * 0.95;
    const total = adultSum + discountSum;
    return { adultSum, discountSum, total };
  };

  return (
    <div className="container" style={{ padding: 20 }}>
      <h2>Поиск рейсов</h2>
      <form
        onSubmit={handleSearchTours}
        style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 20 }}
      >
        <select
          className="input"
          value={selectedDeparture}
          onChange={e => setSelectedDeparture(e.target.value)}
        >
          <option value="">Откуда</option>
          {departureStops.map(s => (
            <option key={s.id} value={s.id}>{s.stop_name}</option>
          ))}
        </select>

        <select
          className="input"
          value={selectedArrival}
          onChange={e => setSelectedArrival(e.target.value)}
          disabled={!selectedDeparture}
        >
          <option value="">Куда</option>
          {arrivalStops.map(s => (
            <option key={s.id} value={s.id}>{s.stop_name}</option>
          ))}
        </select>

        <PassengerSelector
          adultCount={adultCount}
          discountCount={discountCount}
          onAdultChange={setAdultCount}
          onDiscountChange={setDiscountCount}
        />

        <input
          className="input"
          type="text"
          readOnly
          placeholder="Дата туда"
          value={selectedDepartDate}
          onClick={() => { setShowDepartCal(v => !v); setShowReturnCal(false); }}
        />

        <input
          className="input"
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

        <button type="submit" className="btn btn--primary">Поиск</button>
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
        {outboundTours.map(t => {
          const { adultSum, discountSum, total } = calcPrice(t.price);
          const duration = getDuration(t.departure_time, t.arrival_time);
          return (
            <div key={t.id} style={{ border: '1px solid #ccc', padding: 8, marginBottom: 8 }}>
              <div>
                {formatDate(t.date)} {t.departure_time} {depStopName} → {t.arrival_time} {arrStopName} ({duration})
              </div>
              <div>Цена билета: {t.price.toFixed(2)}</div>
              {adultCount > 0 && (
                <div>
                  {adultCount} взрослых {t.price.toFixed(2)} x {adultCount} = {adultSum.toFixed(2)}
                </div>
              )}
              {discountCount > 0 && (
                <div>
                  {discountCount} льготный {t.price.toFixed(2)} x {discountCount} -5% = {discountSum.toFixed(2)}
                </div>
              )}
              <div>Итого: {total.toFixed(2)}</div>
              <button style={{ marginTop: 8 }} onClick={() => handleOutboundTourSelect(t)}>
                Выбрать
              </button>
            </div>
          );
        })}
      </>
    )}

    {selectedReturnDate && returnTours.length > 0 && (
      <>
        <h3>Рейсы обратно:</h3>
        {returnTours.map(t => {
          const { adultSum, discountSum, total } = calcPrice(t.price);
          const duration = getDuration(t.departure_time, t.arrival_time);
          return (
            <div key={t.id} style={{ border: '1px solid #ccc', padding: 8, marginBottom: 8 }}>
              <div>
                {formatDate(t.date)} {t.departure_time} {arrStopName} → {t.arrival_time} {depStopName} ({duration})
              </div>
              <div>Цена билета: {t.price.toFixed(2)}</div>
              {adultCount > 0 && (
                <div>
                  {adultCount} взрослых {t.price.toFixed(2)} x {adultCount} = {adultSum.toFixed(2)}
                </div>
              )}
              {discountCount > 0 && (
                <div>
                  {discountCount} льготный {t.price.toFixed(2)} x {discountCount} -5% = {discountSum.toFixed(2)}
                </div>
              )}
              <div>Итого: {total.toFixed(2)}</div>
              <button style={{ marginTop: 8 }} onClick={() => handleReturnTourSelect(t)}>
                Выбрать
              </button>
            </div>
          );
        })}
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
          {[...Array(seatCount).keys()].map(idx => (
            <div key={idx} style={{display:'flex',alignItems:'center',gap:4,flexWrap:'wrap'}}>
              <span>Пассажир {idx + 1}</span>
              <input
                type="text"
                placeholder="Имя"
                value={passengerNames[idx]}
                onChange={e => {
                  const arr = [...passengerNames];
                  arr[idx] = e.target.value;
                  setPassengerNames(arr);
                }}
                style={{flexGrow:1,minWidth:120}}
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
              <>
                <button type="button" onClick={handlePay}>Оплатить</button>
                <button type="button" onClick={handleCancel}>Отменить</button>
              </>
            )}
          </div>
        </form>
      </>
    )}
    </div>
  );
}
