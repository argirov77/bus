import React, { useState, useEffect } from 'react';
import '../styles/Calendar.css';

export default function Calendar({ activeDates = [], onSelect }) {
  const initial = activeDates.length ? new Date(activeDates[0]) : new Date();
  const [year, setYear] = useState(initial.getFullYear());
  const [month, setMonth] = useState(initial.getMonth());

  useEffect(() => {
    if (activeDates.length) {
      const first = new Date(activeDates[0]);
      setYear(first.getFullYear());
      setMonth(first.getMonth());
    }
  }, [activeDates]);

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
    days.push({ key: date, day: d, date, active: isActive });
  }

  const handleSelect = (date) => {
    if (onSelect) {
      onSelect(date);
    }
  };

  return (
    <div id="calendar">
      <div className="header">{months[month]} {year}</div>
      <div className="weekdays">
        {weekdays.map((w) => (
          <div key={w}>{w}</div>
        ))}
      </div>
      <div className="days">
        {days.map((item) => (
          item.empty ? (
            <div key={item.key} className="inactive" />
          ) : (
            <div
              key={item.key}
              className={item.active ? 'active' : 'inactive'}
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
