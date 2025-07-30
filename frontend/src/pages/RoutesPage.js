import React, { useState, useEffect } from "react";
import axios from "axios";

import { API } from "../config";
// dnd-kit
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  verticalListSortingStrategy
} from "@dnd-kit/sortable";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import deleteIcon from "../assets/icons/delete.png";

export default function RoutesPage() {
  const [routes, setRoutes] = useState([]);
  const [stops, setStops] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(null);
  const [routeStops, setRouteStops] = useState([]);

  const [newRouteName, setNewRouteName] = useState("");
  const [newStop, setNewStop] = useState({
    stop_id: "",
    arrival_time: "",
    departure_time: ""
  });

  // 1. Загрузка маршрутов и остановок при первом рендере
  useEffect(() => {
    axios.get(`${API}/routes`).then((res) => setRoutes(res.data));
    axios.get(`${API}/stops`).then((res) => setStops(res.data));
  }, []);

  // 2. Загрузка остановок выбранного маршрута
  useEffect(() => {
    if (selectedRoute) {
      axios
        .get(`${API}/routes/${selectedRoute.id}/stops`)
        .then((res) => setRouteStops(res.data))
        .catch((err) => console.error("Ошибка при получении остановок:", err));
    } else {
      setRouteStops([]);
    }
  }, [selectedRoute]);

  // Создание маршрута
  const handleCreateRoute = () => {
    if (!newRouteName.trim()) return;
    axios
      .post(`${API}/routes`, { name: newRouteName, is_demo: false })
      .then((res) => {
        setRoutes([...routes, res.data]);
        setNewRouteName("");
      })
      .catch((err) => console.error("Ошибка создания маршрута:", err));
  };

  // Удаление маршрута
  const handleDeleteRoute = (routeId) => {
    axios.delete(`${API}/routes/${routeId}`).then(() => {
      setRoutes(routes.filter((r) => r.id !== routeId));
      if (selectedRoute && selectedRoute.id === routeId) {
        setSelectedRoute(null);
        setRouteStops([]);
      }
    });
  };

  const handleToggleDemo = (route) => {
    axios
      .put(`${API}/routes/${route.id}/demo`, { is_demo: !route.is_demo })
      .then((res) => {
        setRoutes(routes.map((r) => (r.id === route.id ? res.data : r)));
      })
      .catch((err) => {
        alert(err.response?.data?.detail || "Ошибка обновления демо статуса");
      });
  };

  // Выбор маршрута
  const handleSelectRoute = (route) => {
    setSelectedRoute(route);
  };

  // Добавление новой остановки
  const handleAddStop = (e) => {
    e.preventDefault();
    if (!selectedRoute) return;

    const { stop_id, arrival_time, departure_time } = newStop;
    if (!stop_id || !arrival_time || !departure_time) {
      alert("Все поля обязательны!");
      return;
    }
    const maxOrder = routeStops.length ? Math.max(...routeStops.map((rs) => rs.order)) : 0;
    const arr = arrival_time.length === 5 ? arrival_time + ":00" : arrival_time;
    const dep = departure_time.length === 5 ? departure_time + ":00" : departure_time;

    const data = {
      stop_id: Number(stop_id),
      order: maxOrder + 1,
      arrival_time: arr,
      departure_time: dep
    };

    axios
      .post(`${API}/routes/${selectedRoute.id}/stops`, data)
      .then((res) => {
        setRouteStops([...routeStops, res.data]);
        setNewStop({ stop_id: "", arrival_time: "", departure_time: "" });
      })
      .catch((err) => console.error("Ошибка добавления остановки:", err));
  };

  // Удаление остановки
  const handleDeleteStop = (stopId) => {
    if (!selectedRoute) return;
    axios
      .delete(`${API}/routes/${selectedRoute.id}/stops/${stopId}`)
      .then(() => {
        const updated = routeStops
          .filter((rs) => rs.id !== stopId)
          .map((rs, idx) => ({ ...rs, order: idx + 1 }));
        setRouteStops(updated);
        // Сохраняем пересчитанный order
        updated.forEach((rs) => {
          axios.put(`${API}/routes/${selectedRoute.id}/stops/${rs.id}`, rs);
        });
      })
      .catch((err) => console.error("Ошибка удаления остановки:", err));
  };

  // Изменение времени (inline)
  const handleUpdateTime = (stopId, field, value) => {
    const updatedStops = routeStops.map((stop) =>
      stop.id === stopId ? { ...stop, [field]: value + ":00" } : stop
    );
    setRouteStops(updatedStops);

    axios.put(
      `${API}/routes/${selectedRoute.id}/stops/${stopId}`,
      updatedStops.find((s) => s.id === stopId)
    );
  };

  // Настройка Drag & Drop
  const sensors = useSensors(useSensor(PointerSensor));
  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return;
    const oldIndex = routeStops.findIndex((item) => item.id === +active.id);
    const newIndex = routeStops.findIndex((item) => item.id === +over.id);
    if (oldIndex < 0 || newIndex < 0) return;

    const newOrder = arrayMove(routeStops, oldIndex, newIndex).map((rs, idx) => ({
      ...rs,
      order: idx + 1
    }));
    setRouteStops(newOrder);
    newOrder.forEach((rs) => {
      axios.put(`${API}/routes/${selectedRoute.id}/stops/${rs.id}`, rs);
    });
  };

  // Получить имя остановки по id
  const getStopName = (stop_id) => {
    const found = stops.find((s) => s.id === stop_id);
    return found ? found.stop_name : "—";
  };

  return (
    <div className="container">
      <h1>Маршруты</h1>
  
      <div className="routes-wrapper">
        {routes.map((route) => (
          <div key={route.id} className="route-item">
            <button
              className={`route-btn ${selectedRoute?.id === route.id ? "active" : ""}`}
              onClick={() => handleSelectRoute(route)}
            >
              {route.name}
            </button>
            <label style={{ marginLeft: '4px' }}>
              <input
                type="checkbox"
                checked={route.is_demo}
                onChange={() => handleToggleDemo(route)}
              />
              demo
            </label>
            <button
              className="icon-btn"
              onClick={() => handleDeleteRoute(route.id)}
            >
              <img src={deleteIcon} alt="Удалить маршрут" width={20} />
            </button>
          </div>
        ))}
      </div>

  
      <div style={{ marginBottom: "2rem", display: 'flex', gap: '8px' }}>
        <input
          type="text"
          placeholder="Название маршрута"
          value={newRouteName}
          onChange={(e) => setNewRouteName(e.target.value)}
        />
        <button onClick={handleCreateRoute}>Создать</button>
      </div>
  
      {selectedRoute && (
        <>
          <h2>Остановки маршрута: {selectedRoute.name}</h2>
  
          <div className="stop-header">
            <div>Остановка</div>
            <div style={{ textAlign: 'center' }}>Прибытие</div>
            <div style={{ textAlign: 'center' }}>Отправление</div>
            <div></div>
          </div>
  
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={routeStops} strategy={verticalListSortingStrategy}>
              {routeStops.map(rs => (
                <SortableStop
                  key={rs.id}
                  id={rs.id}
                  routeStop={rs}
                  getStopName={getStopName}
                  onDeleteStop={handleDeleteStop}
                  onUpdateTime={handleUpdateTime}
                />
              ))}
            </SortableContext>
          </DndContext>
  
          <h3>Добавить остановку</h3>
          <form onSubmit={handleAddStop} className="add-stop-form">
            <select
              value={newStop.stop_id}
              onChange={(e) => setNewStop({ ...newStop, stop_id: e.target.value })}
            >
              <option value="">Выберите остановку</option>
              {stops.map((s) => (
                <option key={s.id} value={s.id}>{s.stop_name}</option>
              ))}
            </select>
            <input
              type="time"
              value={newStop.arrival_time}
              onChange={(e) => setNewStop({ ...newStop, arrival_time: e.target.value })}
            />
            <input
              type="time"
              value={newStop.departure_time}
              onChange={(e) => setNewStop({ ...newStop, departure_time: e.target.value })}
            />
            <button type="submit">Добавить остановку</button>
          </form>
        </>
      )}
    </div>
  );
  
}

// Компонент для одной остановки
function SortableStop({ id, routeStop, getStopName, onDeleteStop, onUpdateTime }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
  
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    display: "grid",
    gridTemplateColumns: "1fr 110px 110px 40px",
    gap: "8px",
    alignItems: "center",
    marginBottom: "8px",
    background: "#fff",
    borderRadius: "8px",
    boxShadow: "0 2px 5px rgba(0,0,0,0.1)",
    padding: "12px 16px"
  };

  return (
    <div ref={setNodeRef} style={style} className="sortable-stop" {...attributes} {...listeners}>
      <div>
        <strong>{getStopName(routeStop.stop_id)}</strong>
        <div style={{ fontSize: "0.85rem", color: "#666" }}>
          Порядок: {routeStop.order}
        </div>
      </div>
  
      <div>
        <input
          type="time"
          value={routeStop.arrival_time.slice(0, 5)}
          onChange={(e) => onUpdateTime(id, "arrival_time", e.target.value)}
        />
      </div>
  
      <div>
        <input
          type="time"
          value={routeStop.departure_time.slice(0, 5)}
          onChange={(e) => onUpdateTime(id, "departure_time", e.target.value)}
        />
      </div>
  
      <button
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          onDeleteStop(id);
        }}
        className="icon-btn"
      >
        <img src={deleteIcon} alt="Удалить" width="20"/>
      </button>
    </div>
  );
  
}
