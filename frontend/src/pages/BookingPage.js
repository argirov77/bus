import React, { useState } from "react";
import axios from "axios";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";

import { API } from "../config";
import SeatSelection from "../components/SeatSelection";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import styles from "./BookingPage.module.css";
import { downloadTicketPdf } from "../utils/ticket";

function BookingPage(props) {
  const { tourId, departureStopId, arrivalStopId } = props;

  const [selectedSeat, setSelectedSeat] = useState(null);
  const [passengerData, setPassengerData] = useState({ name: "", phone: "", email: "" });
  const [extraBaggage, setExtraBaggage] = useState(false);
  const [bookingMessage, setBookingMessage] = useState("");
  const [bookingType, setBookingType] = useState("info");
  const [loading, setLoading] = useState(false);
  const [purchaseId, setPurchaseId] = useState(null);
  const [issuedTickets, setIssuedTickets] = useState([]);

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
    setIssuedTickets([]);
    axios
      .post(`${API}/book`, {
        tour_id: tourId,
        seat_nums: [selectedSeat],
        passenger_names: [passengerData.name],
        passenger_phone: passengerData.phone,
        passenger_email: passengerData.email,
        departure_stop_id: departureStopId,
        arrival_stop_id: arrivalStopId,
        adult_count: 1,
        discount_count: 0,
        extra_baggage: [extraBaggage]
      })
      .then(function(res) {
        setBookingMessage(`Билет успешно забронирован! Purchase ID: ${res.data.purchase_id}. Сумма: ${res.data.amount_due.toFixed(2)}`);
        setPurchaseId(res.data.purchase_id);
        setIssuedTickets(res.data.tickets || []);
        setBookingType("success");
        setSelectedSeat(null);
        setPassengerData({ name: "", phone: "", email: "" });
        setExtraBaggage(false);
      })
      .catch(function(err) {
        console.error("Ошибка бронирования:", err);
        setBookingMessage("Ошибка при бронировании.");
        setBookingType("error");
        setIssuedTickets([]);
      })
      .finally(() => setLoading(false));
  };

  const handleTicketDownload = async (ticket) => {
    try {
      await downloadTicketPdf(ticket.ticket_id, { deepLink: ticket.deep_link });
    } catch (err) {
      console.error("Не удалось скачать билет", err);
      window.alert("Не удалось скачать билет. Попробуйте ещё раз.");
    }
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
      {issuedTickets.length > 0 && (
        <div className={styles['download-section']}>
          <h3>Ваши билеты</h3>
          <ul>
            {issuedTickets.map((ticket) => (
              <li key={ticket.ticket_id}>
                Билет №{ticket.ticket_id}
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => handleTicketDownload(ticket)}
                >
                  Скачать
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default BookingPage;

