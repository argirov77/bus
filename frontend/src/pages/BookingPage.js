import React, { useState } from "react";
import axios from "axios";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";

import { API } from "../config";
import SeatSelection from "../components/SeatSelection";
import styles from "./BookingPage.module.css";

function BookingPage(props) {
  // Параметры должны быть переданы через props (например, из SearchPage или выбранного тура)
  const { tourId, departureStopId, arrivalStopId } = props;
  
  const [selectedSeat, setSelectedSeat] = useState(null);
  const [passengerData, setPassengerData] = useState({ name: "", phone: "", email: "" });
  const [bookingMessage, setBookingMessage] = useState("");

  // Обработчик выбора места из компонента SeatSelection
  const handleSeatSelect = function(seat) {
    setSelectedSeat(seat.seat_number);
  };

  // Обработчик бронирования (создания билета)
  const handleBooking = function(e) {
    e.preventDefault();
    if (!selectedSeat) {
      setBookingMessage("Выберите место!");
      return;
    }
    axios
      .post(`${API}/tickets`, {
        tour_id: tourId,
        seat_num: selectedSeat,
        passenger_name: passengerData.name,
        passenger_phone: passengerData.phone,
        passenger_email: passengerData.email,
        departure_stop_id: departureStopId,
        arrival_stop_id: arrivalStopId
      })
      .then(function(res) {
        setBookingMessage("Билет успешно забронирован! Ticket ID: " + res.data.ticket_id);
        // Сброс выбранного места и данных пассажира
        setSelectedSeat(null);
        setPassengerData({ name: "", phone: "", email: "" });
      })
      .catch(function(err) {
        console.error("Ошибка бронирования:", err);
        setBookingMessage("Ошибка при бронировании.");
      });
  };

  return (
    <div className={styles.container}>
      <h2>Бронирование билета</h2>
      
      <div className={styles['seat-section']}>
        <h3>Выберите место в салоне</h3>
        <SeatSelection 
          tourId={tourId}
          departureStopId={departureStopId}
          arrivalStopId={arrivalStopId}
          onSelect={handleSeatSelect}
        />
        {selectedSeat && <p>Вы выбрали место: {selectedSeat}</p>}
      </div>

      <div className={styles['passenger-section']}>
        <h3>Введите данные пассажира</h3>
        <form onSubmit={handleBooking} className={styles['booking-form']}>
          <TextField
            label="Имя"
            variant="outlined"
            size="small"
            value={passengerData.name}
            onChange={(e) => setPassengerData({ ...passengerData, name: e.target.value })}
            required
          />
          <TextField
            label="Телефон"
            variant="outlined"
            size="small"
            value={passengerData.phone}
            onChange={(e) => setPassengerData({ ...passengerData, phone: e.target.value })}
          />
          <TextField
            label="Email"
            type="email"
            variant="outlined"
            size="small"
            value={passengerData.email}
            onChange={(e) => setPassengerData({ ...passengerData, email: e.target.value })}
          />
          <Button variant="contained" type="submit">Забронировать</Button>
        </form>
      </div>

      {bookingMessage && <p className={styles['booking-message']}>{bookingMessage}</p>}
    </div>
  );
}

export default BookingPage;
