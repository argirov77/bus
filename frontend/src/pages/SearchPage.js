import React, { useState, useEffect } from "react";
import axios from "axios";
import SeatSelection from "../components/SeatSelection";

function SearchPage() {
  const [departureStops, setDepartureStops] = useState([]);
  const [arrivalStops, setArrivalStops] = useState([]);
  const [dates, setDates] = useState([]);
  const [selectedDeparture, setSelectedDeparture] = useState("");
  const [selectedArrival, setSelectedArrival] = useState("");
  const [selectedDate, setSelectedDate] = useState("");

  const [tours, setTours] = useState([]);
  const [selectedTour, setSelectedTour] = useState(null);

  const [seats, setSeats] = useState([]);
  const [selectedSeat, setSelectedSeat] = useState(null);

  const [passengerData, setPassengerData] = useState({ name: "", phone: "", email: "" });
  const [message, setMessage] = useState("");
  const [selectedLayout, setSelectedLayout] = useState(null);

  // Загрузка отправных остановок
  useEffect(() => {
    axios.get("http://127.0.0.1:8000/search/departures")
      .then(res => setDepartureStops(res.data))
      .catch(err => console.error("Ошибка получения отправных остановок:", err));
  }, []);

  // При выборе отправной, загрузка конечных остановок
  useEffect(() => {
    if (selectedDeparture) {
      axios.get(`http://127.0.0.1:8000/search/arrivals?departure_stop_id=${selectedDeparture}`)
        .then(res => setArrivalStops(res.data))
        .catch(err => console.error("Ошибка получения конечных остановок:", err));
    } else {
      setArrivalStops([]);
      setDates([]);
      setTours([]);
      setSelectedTour(null);
      setSeats([]);
      setSelectedSeat(null);
    }
  }, [selectedDeparture]);

  // При выборе отправной и конечной, загрузка дат
  useEffect(() => {
    if (selectedDeparture && selectedArrival) {
      axios.get(`http://127.0.0.1:8000/search/dates?departure_stop_id=${selectedDeparture}&arrival_stop_id=${selectedArrival}`)
        .then(res => setDates(res.data))
        .catch(err => console.error("Ошибка получения дат:", err));
    } else {
      setDates([]);
      setTours([]);
      setSelectedTour(null);
      setSeats([]);
      setSelectedSeat(null);
    }
  }, [selectedDeparture, selectedArrival]);

  const handleSearchTours = (e) => {
    e.preventDefault();
    if (!selectedDeparture || !selectedArrival || !selectedDate) {
      setMessage("Заполните все поля поиска");
      return;
    }
    setMessage("Поиск туров...");
    axios.get("http://127.0.0.1:8000/tours/search", {
      params: {
        departure_stop_id: selectedDeparture,
        arrival_stop_id: selectedArrival,
        date: selectedDate,
      },
    })
    .then(res => {
      setTours(res.data);
      setSelectedTour(null);
      setSeats([]);
      setSelectedSeat(null);
      setMessage(res.data.length ? "" : "Нет туров для выбранных параметров");
    })
    .catch(err => {
      console.error("Ошибка поиска туров:", err);
      setMessage("Ошибка поиска туров");
    });
  };

  const handleTourSelect = (tour) => {
    setSelectedTour(tour);
    setSelectedSeat(null);
    setSeats([]);
    // Получаем раскладку мест для выбранного тура
    axios.get("http://127.0.0.1:8000/seat", {
      params: {
        tour_id: tour.id,
        departure_stop_id: selectedDeparture,
        arrival_stop_id: selectedArrival
      },
    })
    .then(res => {
      setSeats(res.data.seats);
      setSelectedLayout(res.data.layout_variant);
    })
    .catch(err => {
      console.error("Ошибка загрузки мест:", err);
      setSeats([]);
    });
  };

  const handleBooking = (e) => {
    e.preventDefault();
    if (!selectedTour) {
      setMessage("Сначала выберите тур");
      return;
    }
    if (!selectedSeat) {
      setMessage("Сначала выберите место");
      return;
    }
    axios.post("http://127.0.0.1:8000/tickets", {
      tour_id: selectedTour.id,
      seat_num: selectedSeat,
      passenger_name: passengerData.name,
      passenger_phone: passengerData.phone,
      passenger_email: passengerData.email,
      departure_stop_id: Number(selectedDeparture),
      arrival_stop_id: Number(selectedArrival)
    })
    .then(res => {
      setMessage(`Билет забронирован! Ticket ID: ${res.data.ticket_id}`);
      setSelectedSeat(null);
      setPassengerData({ name: "", phone: "", email: "" });
    })
    .catch(err => {
      console.error("Ошибка при бронировании:", err);
      setMessage("Ошибка при бронировании");
    });
  };

  return (
    <div className="container" style={{ padding: "20px" }}>
      <h2>Поиск рейсов</h2>
      <form onSubmit={handleSearchTours} style={{ marginBottom: "20px" }}>
        <select value={selectedDeparture} onChange={(e) => setSelectedDeparture(e.target.value)}>
          <option value="">Откуда</option>
          {departureStops.map(s => (
            <option key={s.id} value={s.id}>{s.stop_name}</option>
          ))}
        </select>
        <select value={selectedArrival} onChange={(e) => setSelectedArrival(e.target.value)}>
          <option value="">Куда</option>
          {arrivalStops.map(s => (
            <option key={s.id} value={s.id}>{s.stop_name}</option>
          ))}
        </select>
        <select value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)}>
          <option value="">Дата</option>
          {dates.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <button type="submit">Найти рейсы</button>
      </form>
      {message && <p>{message}</p>}
      {tours.length > 0 && !selectedTour && (
        <div>
          <h3>Выберите рейс</h3>
          {tours.map(tour => (
            <div key={tour.id} style={{ marginBottom: "10px" }}>
              <p>Рейс #{tour.id}, Дата: {tour.date}, Доступно мест: {tour.seats}</p>
              <button onClick={() => handleTourSelect(tour)}>Выбрать</button>
            </div>
          ))}
        </div>
      )}
      {selectedTour && (
        <>
          <h3>Выбранный рейс: #{selectedTour.id}</h3>
          <p>Дата: {selectedTour.date}</p>
          <p>Доступно мест: {selectedTour.seats}</p>
          <p>Выберите место для бронирования:</p>
          {selectedLayout && (
            <SeatSelection
              seats={seats}
              onSelect={(seat) => setSelectedSeat(seat.seat_num)}
            />
          )}
          {selectedSeat && <p>Вы выбрали место: {selectedSeat}</p>}
          <form onSubmit={handleBooking} style={{ marginTop: "20px" }}>
            <input
              type="text"
              placeholder="Имя"
              required
              value={passengerData.name}
              onChange={(e) => setPassengerData({ ...passengerData, name: e.target.value })}
            />
            <input
              type="text"
              placeholder="Телефон"
              value={passengerData.phone}
              onChange={(e) => setPassengerData({ ...passengerData, phone: e.target.value })}
            />
            <input
              type="email"
              placeholder="Email"
              value={passengerData.email}
              onChange={(e) => setPassengerData({ ...passengerData, email: e.target.value })}
            />
            <button type="submit">Забронировать</button>
          </form>
        </>
      )}
    </div>
  );
}

export default SearchPage;
