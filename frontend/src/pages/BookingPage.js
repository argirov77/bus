import React, { useState } from "react";
import axios from "axios";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";

import { API } from "../config";
import SeatSelection from "../components/SeatSelection";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import styles from "./BookingPage.module.css";

function BookingPage(props) {
  const { tourId, departureStopId, arrivalStopId } = props;

  const [selectedSeat, setSelectedSeat] = useState(null);
  const [passengerData, setPassengerData] = useState({ name: "", phone: "", email: "" });
  const [extraBaggage, setExtraBaggage] = useState(false);
  const [bookingMessage, setBookingMessage] = useState("");
  const [bookingType, setBookingType] = useState("info");
  const [loading, setLoading] = useState(false);

  const handleSeatSelect = function(seat) {
    setSelectedSeat(seat.seat_number);
  };

  const handleBooking = function(e) {
    e.preventDefault();
    if (!selectedSeat) {
      setBookingMessage("Выберите место!");
      setBookingType("error");
      return;
    }
    setBookingMessage("Бронирование…");
    setBookingType("info");
    setLoading(true);
    axios
      .post(`${API}/tickets`, {
        tour_id: tourId,
        seat_num: selectedSeat,
        passenger_name: passengerData.name,
        passenger_phone: passengerData.phone,
        passenger_email: passengerData.email,
        departure_stop_id: departureStopId,
        arrival_stop_id: arrivalStopId,
        extra_baggage: extraBaggage
      })
      .then(function(res) {
        setBookingMessage("Билет успешно забронирован! Ticket ID: " + res.data.ticket_id);
        setBookingType("success");
        setSelectedSeat(null);
        setPassengerData({ name: "", phone: "", email: "" });
        setExtraBaggage(false);
      })
      .catch(function(err) {
        console.error("Ошибка бронирования:", err);
        setBookingMessage("Ошибка при бронировании.");
        setBookingType("error");
      })
      .finally(() => setLoading(false));
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
          <label style={{display:'flex',alignItems:'center',gap:4}}>
            <input
              type="checkbox"
              checked={extraBaggage}
              onChange={e => setExtraBaggage(e.target.checked)}
            />
            Дополнительный багаж
          </label>
          <Button variant="contained" type="submit">Забронировать</Button>
        </form>
      </div>
      {loading && <Loader />}
      {bookingMessage && (
        <Alert type={bookingType} message={bookingMessage} />
      )}
    </div>
  );
}

export default BookingPage;

