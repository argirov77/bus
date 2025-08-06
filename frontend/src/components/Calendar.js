import React, { useState, useEffect } from 'react';
import '../styles/Calendar.css';

// Calendar with month navigation and date selection.
// `activeDates` - array of ISO date strings that are selectable.
// `selectedDate` - currently chosen date (ISO string).
// `onSelect` - callback when user chooses a date.
export default function Calendar({ activeDates = [], selectedDate = '', onSelect }) {
  // initial month/year based on selected date or first active date
  const initial = selectedDate
    ? new Date(selectedDate)
    : activeDates.length
      ? new Date(activeDates[0])
      : new Date();

  const [year, setYear] = useState(initial.getFullYear());
  const [month, setMonth] = useState(initial.getMonth());

  // When the list of active dates or selected date changes, make sure
  // the calendar shows the month that contains that date
  useEffect(() => {
    const src = selectedDate || (activeDates.length ? activeDates[0] : null);
    if (src) {
      const d = new Date(src);
      setYear(d.getFullYear());
      setMonth(d.getMonth());
    }
  }, [activeDates, selectedDate]);

  const prevMonth = () => {
    setMonth((m) => {
      if (m === 0) {
        setYear((y) => y - 1);
        return 11;
      }
      return m - 1;
    });
  };

  const nextMonth = () => {
    setMonth((m) => {
      if (m === 11) {
        setYear((y) => y + 1);
        return 0;
      }
      return m + 1;
    });
  };

  const months = [
    'Январь','Февраль','Март','Апрель','Май','Июнь',
    'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'
  ];
  const weekdays = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startDay = (firstDay.getDay() + 6) % 7;
  const daysInMonth = lastDay.getDate();

  const days = [];
  for (let i = 0; i < startDay; i++) {
    days.push({ key: `e${i}`, empty: true });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(year, month, d).toISOString().slice(0, 10);
    const isActive = activeDates.includes(date);
    const isSelected = selectedDate === date;
    days.push({ key: date, day: d, date, active: isActive, selected: isSelected });
  }

  const handleSelect = (date) => {
    if (onSelect) {
      onSelect(date);
    }
  };

  return (
    <div id="calendar">
      <div className="header">
        <button className="nav prev" onClick={prevMonth}>&lt;</button>
        <span>{months[month]} {year}</span>
        <button className="nav next" onClick={nextMonth}>&gt;</button>
      </div>
      <div className="weekdays">
        {weekdays.map((w) => (
          <div key={w}>{w}</div>
        ))}
      </div>
      <div className="days">
        {days.map((item) => (
          item.empty ? (
            <div key={item.key} className="empty" />
          ) : (
            <div
              key={item.key}
              className={
                item.selected
                  ? 'selected'
                  : item.active
                    ? 'active'
                    : 'inactive'
              }
              onClick={item.active ? () => handleSelect(item.date) : undefined}
            >
              {item.day}
            </div>
          )
        ))}
      </div>
    </div>
  );
}
