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
  const [newStopName, setNewStopName] = useState("");
  const [editingStopId, setEditingStopId] = useState(null);
  const [editingStopName, setEditingStopName] = useState("");

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
    if (!newStopName.trim()) return;
    axios.post(`${API}/stops`, { stop_name: newStopName })
      .then(res => {
        setStops([...stops, res.data]);
        setNewStopName("");
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
    setEditingStopName(stop.stop_name);
  };

  const handleUpdateStop = (e) => {
    e.preventDefault();
    axios.put(`${API}/stops/${editingStopId}`, { stop_name: editingStopName })
      .then(res => {
        setStops(stops.map(stop => stop.id === editingStopId ? res.data : stop));
        setEditingStopId(null);
        setEditingStopName("");
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
              <form onSubmit={handleUpdateStop}>
                <input
                  type="text"
                  value={editingStopName}
                  onChange={(e) => setEditingStopName(e.target.value)}
                />
                <button type="submit">Сохранить</button>
                <button type="button" onClick={() => setEditingStopId(null)}>
                  Отмена
                </button>
              </form>
            ) : (
              <div className="stop-row">
                <span>{stop.stop_name}</span>
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
      <form onSubmit={handleCreateStop}>
        <input
          type="text"
          placeholder="Название остановки"
          value={newStopName}
          onChange={(e) => setNewStopName(e.target.value)}
        />
        <IconButton icon={addIcon} alt="Добавить" onClick={handleCreateStop} />
      </form>
    </div>
  );
}

export default StopsPage;
