// src/pages/StopsPage.js
import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../config";
import IconButton from "../components/IconButton";
import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import addIcon from "../assets/icons/add.png";

const LANGS = ["ru", "en", "bg", "ua"];

const emptyStop = {
  stop_name: "",   // ru
  stop_en: "",
  stop_bg: "",
  stop_ua: "",
  description: "",
  location: "",
};

function useLangNames(initial) {
  const [names, setNames] = useState({
    ru: initial.stop_name || "",
    en: initial.stop_en || "",
    bg: initial.stop_bg || "",
    ua: initial.stop_ua || "",
  });
  const setFor = (lang, val) =>
    setNames((p) => ({ ...p, [lang]: val }));

  const packToPayload = (extra = {}) => ({
    stop_name: names.ru,
    stop_en: names.en,
    stop_bg: names.bg,
    stop_ua: names.ua,
    ...extra,
  });

  return { names, setFor, packToPayload };
}

function StopForm({ initial, onSubmit, onCancel, submitText = "Сохранить" }) {
  const [active, setActive] = useState("ru");
  const { names, setFor, packToPayload } = useLangNames(initial || emptyStop);
  const [description, setDescription] = useState(initial.description || "");
  const [location, setLocation] = useState(initial.location || "");

  const handleSubmit = (e) => {
    e.preventDefault();
    const hasAny = Object.values(names).some((v) => v && v.trim().length);
    if (!hasAny) return;
    onSubmit(
      packToPayload({
        description: description.trim(),
        location: location.trim(),
      })
    );
  };

  return (
    <form onSubmit={handleSubmit} className="stop-card">
      <div className="lang-tabs">
        {LANGS.map((l) => (
          <button
            key={l}
            type="button"
            className={active === l ? "active" : ""}
            onClick={() => setActive(l)}
          >
            {l.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="field">
        <label>Название ({active.toUpperCase()})</label>
        <input
          type="text"
          placeholder={`Название (${active.toUpperCase()})`}
          value={names[active]}
          onChange={(e) => setFor(active, e.target.value)}
        />
      </div>

      <div className="field">
        <label>Описание</label>
        <textarea
          rows="3"
          placeholder="Короткое описание…"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className="field">
        <label>Ссылка на карту</label>
        <input
          type="url"
          placeholder="https://maps.google.com/…"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
        />
      </div>

      <div className="actions">
        <button className="btn primary" type="submit">{submitText}</button>
        {onCancel && (
          <button className="btn" type="button" onClick={onCancel}>
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}

export default function StopsPage() {
  const [stops, setStops] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [creatingOpen, setCreatingOpen] = useState(false);

  useEffect(() => { fetchStops(); }, []);
  const fetchStops = () =>
    axios.get(`${API}/stops`)
      .then((r) => setStops(r.data))
      .catch((e) => console.error("Ошибка при загрузке остановок:", e));

  const handleCreate = (payload) =>
    axios.post(`${API}/stops`, payload)
      .then((r) => {
        setStops((s) => [...s, r.data]);
        setCreatingOpen(false);
      })
      .catch((e) => console.error("Ошибка создания остановки:", e));

  const handleUpdate = (payload) =>
    axios.put(`${API}/stops/${editingId}`, payload)
      .then((r) => {
        setStops((s) => s.map((x) => (x.id === editingId ? r.data : x)));
        setEditingId(null);
      })
      .catch((e) => console.error("Ошибка обновления остановки:", e));

  const handleDelete = (id) =>
    axios.delete(`${API}/stops/${id}`)
      .then(() => setStops((s) => s.filter((x) => x.id !== id)))
      .catch((e) => console.error("Ошибка удаления остановки:", e));

  return (
    <div className="container">
      <h2>Остановки</h2>

      <ul className="stop-list">
        {stops.map((stop) => (
          <li key={stop.id} className="stop-row card-row">
            {editingId === stop.id ? (
              <StopForm
                initial={stop}
                onSubmit={handleUpdate}
                onCancel={() => setEditingId(null)}
                submitText="Сохранить"
              />
            ) : (
              <>
                <div className="stop-title">
                  <strong>{stop.stop_name}</strong>
                  {stop.location && (
                    <a
                      href={stop.location}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="stop-location-link"
                    >
                      Карта
                    </a>
                  )}
                  {stop.description ? (
                    <span className="muted"> — {stop.description}</span>
                  ) : null}
                </div>
                <div className="stop-actions">
                  <IconButton
                    icon={editIcon}
                    alt="Редактировать"
                    onClick={() => setEditingId(stop.id)}
                  />
                  <IconButton
                    icon={deleteIcon}
                    alt="Удалить"
                    onClick={() => handleDelete(stop.id)}
                  />
                </div>
              </>
            )}
          </li>
        ))}
      </ul>

      <div className="create-wrap">
        <button
          className="btn primary"
          onClick={() => setCreatingOpen((v) => !v)}
        >
          {creatingOpen ? "Скрыть" : "Добавить остановку"}
        </button>

        {creatingOpen && (
          <div className="card-row">
            <StopForm
              initial={emptyStop}
              onSubmit={handleCreate}
              submitText="Добавить"
            />
          </div>
        )}
      </div>
    </div>
  );
}

