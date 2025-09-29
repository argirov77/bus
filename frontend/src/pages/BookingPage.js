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

  const formatDate = (value) => {
    if (!value) {
      return "";
    }
    const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (isoMatch) {
      return `${isoMatch[3]}.${isoMatch[2]}.${isoMatch[1]}`;
    }
    try {
      const parsed = new Date(value);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed.toLocaleDateString("ru-RU");
      }
    } catch (err) {
      // ignore formatting errors and fall back to the original value
    }
    return value;
  };

  const formatDuration = (ticket) => {
    if (!ticket) {
      return "";
    }
    if (ticket.duration_text) {
      return ticket.duration_text;
    }
    if (typeof ticket.duration_minutes === "number") {
      const hours = Math.floor(ticket.duration_minutes / 60);
      const minutes = ticket.duration_minutes % 60;
      const parts = [];
      if (hours) {
        parts.push(`${hours} ч`);
      }
      if (minutes) {
        parts.push(`${minutes} мин`);
      }
      if (!parts.length) {
        parts.push("0 мин");
      }
      return parts.join(" ");
    }
    return "";
  };

  const renderStopDetails = (stop = {}, label, tripDate) => {
    const location = stop.location;
    const hasUrl = typeof location === "string" && /^https?:\/\//i.test(location);

    return (
      <div className={styles.ticketRow}>
        <div className={styles.ticketLabel}>{label}</div>
        <div className={styles.ticketValue}>
          <div className={styles.stopName}>{stop.name || "—"}</div>
          {(tripDate || stop.time) && (
            <div className={styles.stopMeta}>
              {tripDate && <span>{tripDate}</span>}
              {tripDate && stop.time && <span>·</span>}
              {stop.time && <span>{stop.time}</span>}
            </div>
          )}
          {stop.description && (
            <div className={styles.stopDescription}>{stop.description}</div>
          )}
          {location && hasUrl && (
            <a
              className={styles.stopLocation}
              href={location}
              target="_blank"
              rel="noopener noreferrer"
            >
              Посмотреть на карте
            </a>
          )}
          {location && !hasUrl && (
            <div className={styles.stopLocation}>{location}</div>
          )}
        </div>
      </div>
    );
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
        <div className={styles.downloadSection}>
          <h3>Ваши билеты</h3>
          <div className={styles.ticketList}>
            {issuedTickets.map((ticket) => {
              const departure = ticket?.departure || {};
              const arrival = ticket?.arrival || {};
              const tripDate = ticket.trip_date_text || formatDate(ticket.trip_date);
              const duration = formatDuration(ticket);

              return (
                <article key={ticket.ticket_id} className={styles.ticketCard}>
                  <header className={styles.ticketHeader}>
                    <div>
                      <h4 className={styles.ticketTitle}>Билет №{ticket.ticket_id}</h4>
                      <div className={styles.ticketMeta}>
                        {ticket.route_label && (
                          <span className={styles.ticketTag}>{ticket.route_label}</span>
                        )}
                        {tripDate && (
                          <span className={styles.ticketTag}>Дата: {tripDate}</span>
                        )}
                        {ticket.seat_number && (
                          <span className={styles.ticketTag}>Место {ticket.seat_number}</span>
                        )}
                        {duration && (
                          <span className={styles.ticketTag}>В пути: {duration}</span>
                        )}
                      </div>
                    </div>
                    <div className={styles.ticketActions}>
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={() => handleTicketDownload(ticket)}
                      >
                        Скачать PDF
                      </Button>
                      {ticket.deep_link && (
                        <a
                          className={styles.ticketLink}
                          href={ticket.deep_link}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Управлять поездкой
                        </a>
                      )}
                    </div>
                  </header>
                  <div className={styles.ticketBody}>
                    {renderStopDetails(departure, "Отправление", tripDate)}
                    <div className={styles.ticketDivider} />
                    {renderStopDetails(arrival, "Прибытие", tripDate)}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default BookingPage;

