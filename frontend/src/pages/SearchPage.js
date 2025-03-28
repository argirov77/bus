import React, { useState, useEffect } from "react";
import axios from "axios";
import SeatSelection from "../components/SeatSelection"; // компонент выбора мест

function SearchPage() {
  // Шаг 1–3: Остановки отправления и прибытия, список дат
  const [departureStops, setDepartureStops] = useState([]);
  const [arrivalStops, setArrivalStops] = useState([]);
  const [dates, setDates] = useState([]);

  // Выбранные значения
  const [selectedDeparture, setSelectedDeparture] = useState("");
  const [selectedArrival, setSelectedArrival] = useState("");
  const [selectedDate, setSelectedDate] = useState("");

  // Шаг 4: Найденные туры (рейсы) и выбранный тур
  const [tours, setTours] = useState([]);
  const [selectedTour, setSelectedTour] = useState(null);

  // Шаг 5: Массив мест, выбранное место, форма пассажира
  const [seats, setSeats] = useState([]);
  const [selectedSeat, setSelectedSeat] = useState(null);
  const [passengerData, setPassengerData] = useState({ name: "", phone: "", email: "" });

  // Сообщения и ошибки
  const [message, setMessage] = useState("");

  // ============================
  // Шаги 1–3: Загрузка "Откуда", "Куда", "Даты"
  // ============================

  // 1. Загрузка списка «Откуда»
  useEffect(() => {
    axios
      .get("http://127.0.0.1:8000/search/departures")
      .then((res) => {
        setDepartureStops(res.data);
      })
      .catch((err) => {
        console.error("Ошибка получения отправных остановок:", err);
      });
  }, []);

  // 2. При выборе отправной остановки, грузим «Куда»
  useEffect(() => {
    if (selectedDeparture) {
      axios
        .get(`http://127.0.0.1:8000/search/arrivals?departure_stop_id=${selectedDeparture}`)
        .then((res) => {
          setArrivalStops(res.data);
        })
        .catch((err) => {
          console.error("Ошибка получения конечных остановок:", err);
        });
    } else {
      // Сброс, если убрали отправную остановку
      setArrivalStops([]);
      setDates([]);
      setTours([]);
      setSelectedTour(null);
      setSeats([]);
      setSelectedSeat(null);
    }
  }, [selectedDeparture]);

  // 3. При выборе отправной и конечной, грузим даты
  useEffect(() => {
    if (selectedDeparture && selectedArrival) {
      axios
        .get(
          `http://127.0.0.1:8000/search/dates?departure_stop_id=${selectedDeparture}&arrival_stop_id=${selectedArrival}`
        )
        .then((res) => {
          setDates(res.data);
        })
        .catch((err) => {
          console.error("Ошибка получения дат:", err);
        });
    } else {
      setDates([]);
      setTours([]);
      setSelectedTour(null);
      setSeats([]);
      setSelectedSeat(null);
    }
  }, [selectedDeparture, selectedArrival]);

  // ============================
  // Шаг 4: Поиск туров
  // ============================
  const handleSearchTours = (e) => {
    e.preventDefault();
    if (!selectedDeparture || !selectedArrival || !selectedDate) {
      setMessage("Заполните все поля поиска");
      return;
    }
    setMessage("Поиск туров...");

    axios
      .get("http://127.0.0.1:8000/tours/search", {
        params: {
          departure_stop_id: selectedDeparture,
          arrival_stop_id: selectedArrival,
          date: selectedDate,
        },
      })
      .then((res) => {
        setTours(res.data);
        setSelectedTour(null);
        setSeats([]);
        setSelectedSeat(null);
        if (res.data.length === 0) {
          setMessage("Нет туров для выбранных параметров");
        } else {
          setMessage("");
        }
      })
      .catch((err) => {
        console.error("Ошибка поиска туров:", err);
        setMessage("Ошибка поиска туров");
      });
  };

  const handleTourSelect = (tour) => {
    setSelectedTour(tour);
    setSelectedSeat(null);
    setSeats([]);
    setMessage("");
  };

  // ============================
  // Шаг 5: Загрузка мест, выбор места, бронирование
  // ============================

  // При выборе конкретного тура (selectedTour), грузим список мест
  useEffect(() => {
    if (selectedTour) {
      // Запрос к эндпоинту /seat
      axios
        .get("http://127.0.0.1:8000/seat", {
          params: {
            tour_id: selectedTour.id,
            departure_stop_id: selectedDeparture,
            arrival_stop_id: selectedArrival,
          },
        })
        .then((res) => {
          setSeats(res.data); // массив { seat_num, available }
        })
        .catch((err) => {
          console.error("Ошибка загрузки мест:", err);
          setSeats([]);
        });
    } else {
      setSeats([]);
    }
  }, [selectedTour, selectedDeparture, selectedArrival]);

  // Колбэк, когда пользователь кликает на место в SeatSelection
  const handleSeatSelection = (seat) => {
    setSelectedSeat(seat.seat_num);
  };

  // Отправка запроса на бронирование
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
    axios
      .post("http://127.0.0.1:8000/tickets", {
        tour_id: selectedTour.id,
        seat_num: selectedSeat,
        passenger_name: passengerData.name,
        passenger_phone: passengerData.phone,
        passenger_email: passengerData.email,
        departure_stop_id: Number(selectedDeparture),
        arrival_stop_id: Number(selectedArrival),
      })
      .then((res) => {
        setMessage(`Билет забронирован! Ticket ID: ${res.data.ticket_id}`);
        // Сброс
        setSelectedSeat(null);
        setPassengerData({ name: "", phone: "", email: "" });
      })
      .catch((err) => {
        console.error("Ошибка при бронировании:", err);
        setMessage("Ошибка при бронировании");
      });
  };

  // ============================
  // Рендер
  // ============================
  return (
    <div className="container" style={{ padding: "20px" }}>
      <h2>Поиск рейсов</h2>

      {/* Форма поиска (шаги 1–3) */}
      <form onSubmit={handleSearchTours} style={{ marginBottom: "20px" }}>
        <label style={{ marginRight: "5px" }}>Откуда:</label>
        <select
          value={selectedDeparture}
          onChange={(e) => setSelectedDeparture(e.target.value)}
          style={{ marginRight: "10px" }}
        >
          <option value="">Выберите остановку</option>
          {departureStops.map((stop) => (
            <option key={stop.id} value={stop.id}>
              {stop.stop_name}
            </option>
          ))}
        </select>

        <label style={{ marginRight: "5px" }}>Куда:</label>
        <select
          value={selectedArrival}
          onChange={(e) => setSelectedArrival(e.target.value)}
          style={{ marginRight: "10px" }}
          disabled={!selectedDeparture}
        >
          <option value="">Выберите остановку</option>
          {arrivalStops.map((stop) => (
            <option key={stop.id} value={stop.id}>
              {stop.stop_name}
            </option>
          ))}
        </select>

        <label style={{ marginRight: "5px" }}>Дата:</label>
        <select
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          style={{ marginRight: "10px" }}
          disabled={!selectedDeparture || !selectedArrival}
        >
          <option value="">Выберите дату</option>
          {dates.map((d, index) => (
            <option key={index} value={d}>
              {d}
            </option>
          ))}
        </select>

        <button type="submit">Найти рейсы</button>
      </form>

      {/* Сообщения/ошибки */}
      {message && <p style={{ color: "blue" }}>{message}</p>}

      {/* Список туров */}
      {tours.length > 0 && !selectedTour && (
        <div>
          <h3>Выберите рейс</h3>
          {tours.map((tour) => (
            <div key={tour.id} style={{ marginBottom: "10px" }}>
              <p>
                Рейс #{tour.id}, Дата: {tour.date}, Доступно мест: {tour.seats}
              </p>
              <button onClick={() => handleTourSelect(tour)}>Выбрать</button>
            </div>
          ))}
        </div>
      )}

      {/* Если выбран тур, показываем схему мест + форму */}
      {selectedTour && (
        <div style={{ marginTop: "20px" }}>
          <h3>Выбранный рейс: #{selectedTour.id}</h3>
          <p>Дата: {selectedTour.date}</p>
          <p>Доступно мест: {selectedTour.seats}</p>
          <p>Далее выберите место и оформите билет.</p>

          {/* Компонент выбора мест */}
          <h4>Выберите место</h4>
          <SeatSelection seats={seats} onSelect={handleSeatSelection} />

          {/* Показать выбранное место */}
          {selectedSeat && <p>Вы выбрали место: {selectedSeat}</p>}

          {/* Если выбрано место, показываем форму пассажира */}
          {selectedSeat && (
            <div style={{ marginTop: "20px" }}>
              <h4>Введите данные пассажира</h4>
              <form onSubmit={handleBooking}>
                <input
                  type="text"
                  placeholder="Имя"
                  value={passengerData.name}
                  onChange={(e) => setPassengerData({ ...passengerData, name: e.target.value })}
                  required
                  style={{ marginBottom: "10px", display: "block" }}
                />
                <input
                  type="text"
                  placeholder="Телефон"
                  value={passengerData.phone}
                  onChange={(e) => setPassengerData({ ...passengerData, phone: e.target.value })}
                  style={{ marginBottom: "10px", display: "block" }}
                />
                <input
                  type="email"
                  placeholder="Email"
                  value={passengerData.email}
                  onChange={(e) => setPassengerData({ ...passengerData, email: e.target.value })}
                  style={{ marginBottom: "10px", display: "block" }}
                />
                <button type="submit">Забронировать</button>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SearchPage;
