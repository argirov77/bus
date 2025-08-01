// src/pages/StopsPage.js
import React, { useState, useEffect } from "react";
import axios from "axios";

import { API } from "../config";
import IconButton from "../components/IconButton";
import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import addIcon from "../assets/icons/add.png";

function StopsPage() {
  const [stops, setStops] = useState([]);
  const emptyStop = {
    stop_name: "",
    stop_en: "",
    stop_bg: "",
    stop_ua: "",
    description: "",
    location: "",
  };
  const [newStop, setNewStop] = useState({ ...emptyStop });
  const [editingStopId, setEditingStopId] = useState(null);
  const [editingStop, setEditingStop] = useState({ ...emptyStop });

  useEffect(() => {
    fetchStops();
  }, []);

  const fetchStops = () => {
    axios.get(`${API}/stops`)
      .then(res => setStops(res.data))
      .catch(err => console.error("Ошибка при загрузке остановок:", err));
  };

  const handleCreateStop = (e) => {
    e.preventDefault();
    if (!newStop.stop_name.trim()) return;
    axios.post(`${API}/stops`, newStop)
      .then(res => {
        setStops([...stops, res.data]);
        setNewStop({ ...emptyStop });
      })
      .catch(err => console.error("Ошибка создания остановки:", err));
  };

  const handleDeleteStop = (id) => {
    axios.delete(`${API}/stops/${id}`)
      .then(() => setStops(stops.filter(s => s.id !== id)))
      .catch(err => console.error("Ошибка удаления остановки:", err));
  };

  const handleEdit = (stop) => {
    setEditingStopId(stop.id);
    setEditingStop({
      stop_name: stop.stop_name || "",
      stop_en: stop.stop_en || "",
      stop_bg: stop.stop_bg || "",
      stop_ua: stop.stop_ua || "",
      description: stop.description || "",
      location: stop.location || "",
    });
  };

  const handleUpdateStop = (e) => {
    e.preventDefault();
    axios.put(`${API}/stops/${editingStopId}`, editingStop)
      .then(res => {
        setStops(stops.map(stop => stop.id === editingStopId ? res.data : stop));
        setEditingStopId(null);
        setEditingStop({ ...emptyStop });
      })
      .catch(err => console.error("Ошибка обновления остановки:", err));
  };

  return (
    <div className="container">
      <h2>Остановки</h2>
      <ul>
        {stops.map(stop => (
          <li key={stop.id} className="card">
            {editingStopId === stop.id ? (
              <form onSubmit={handleUpdateStop} className="stop-edit-form">
                <input
                  type="text"
                  placeholder="RU"
                  value={editingStop.stop_name}
                  onChange={(e) => setEditingStop({ ...editingStop, stop_name: e.target.value })}
                />
                <input
                  type="text"
                  placeholder="EN"
                  value={editingStop.stop_en}
                  onChange={(e) => setEditingStop({ ...editingStop, stop_en: e.target.value })}
                />
                <input
                  type="text"
                  placeholder="BG"
                  value={editingStop.stop_bg}
                  onChange={(e) => setEditingStop({ ...editingStop, stop_bg: e.target.value })}
                />
                <input
                  type="text"
                  placeholder="UA"
                  value={editingStop.stop_ua}
                  onChange={(e) => setEditingStop({ ...editingStop, stop_ua: e.target.value })}
                />
                <textarea
                  placeholder="Описание"
                  value={editingStop.description}
                  onChange={(e) => setEditingStop({ ...editingStop, description: e.target.value })}
                />
                <input
                  type="text"
                  placeholder="Ссылка на карту"
                  value={editingStop.location}
                  onChange={(e) => setEditingStop({ ...editingStop, location: e.target.value })}
                />
                <button type="submit">Сохранить</button>
                <button type="button" onClick={() => setEditingStopId(null)}>Отмена</button>
              </form>
            ) : (
              <div className="stop-row">
                <span>{stop.stop_name}</span>
                {stop.location && (
                  <a href={stop.location} target="_blank" rel="noopener noreferrer" className="stop-location-link">Карта</a>
                )}
                <div className="stop-actions">
                  <IconButton icon={editIcon} alt="Редактировать" onClick={() => handleEdit(stop)} />
                  <IconButton icon={deleteIcon} alt="Удалить" onClick={() => handleDeleteStop(stop.id)} />
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>

      <h3>Добавить новую остановку</h3>
      <form onSubmit={handleCreateStop} className="stop-edit-form">
        <input
          type="text"
          placeholder="RU"
          value={newStop.stop_name}
          onChange={(e) => setNewStop({ ...newStop, stop_name: e.target.value })}
        />
        <input
          type="text"
          placeholder="EN"
          value={newStop.stop_en}
          onChange={(e) => setNewStop({ ...newStop, stop_en: e.target.value })}
        />
        <input
          type="text"
          placeholder="BG"
          value={newStop.stop_bg}
          onChange={(e) => setNewStop({ ...newStop, stop_bg: e.target.value })}
        />
        <input
          type="text"
          placeholder="UA"
          value={newStop.stop_ua}
          onChange={(e) => setNewStop({ ...newStop, stop_ua: e.target.value })}
        />
        <textarea
          placeholder="Описание"
          value={newStop.description}
          onChange={(e) => setNewStop({ ...newStop, description: e.target.value })}
        />
        <input
          type="text"
          placeholder="Ссылка на карту"
          value={newStop.location}
          onChange={(e) => setNewStop({ ...newStop, location: e.target.value })}
        />
        <IconButton icon={addIcon} alt="Добавить" onClick={handleCreateStop} />
      </form>
    </div>
  );
}

export default StopsPage;
