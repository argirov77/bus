import React, { useState, useEffect } from "react";
import axios from "axios";

import BusLayoutNeoplan from "../components/busLayouts/BusLayoutNeoplan";
import BusLayoutTravego from "../components/busLayouts/BusLayoutTravego";

import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import addIcon from "../assets/icons/add.png";
import saveIcon from "../assets/icons/save.png";
import cancelIcon from "../assets/icons/cancel.png";

function ToursPage() {
  const [tours, setTours] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [pricelists, setPricelists] = useState([]);

  // Данные для создания нового тура
  const [newTour, setNewTour] = useState({
    route_id: "",
    pricelist_id: "",
    date: "",
    layout_variant: "",
    activeSeats: []
  });

  // Данные для редактирования тура
  const [editingTourId, setEditingTourId] = useState(null);
  const [editingTourData, setEditingTourData] = useState({
    route_id: "",
    pricelist_id: "",
    date: "",
    layout_variant: "",
    activeSeats: []
  });
  // Состояние раскладки мест для редактирования тура (полученное с сервера)
  const [editingTourSeats, setEditingTourSeats] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = () => {
    axios.get("http://127.0.0.1:8000/tours")
      .then(res => setTours(res.data))
      .catch(err => console.error("Ошибка загрузки туров:", err));
    axios.get("http://127.0.0.1:8000/routes")
      .then(res => setRoutes(res.data))
      .catch(err => console.error("Ошибка загрузки маршрутов:", err));
    axios.get("http://127.0.0.1:8000/pricelists")
      .then(res => setPricelists(res.data))
      .catch(err => console.error("Ошибка загрузки прайслистов:", err));
  };

  // При входе в режим редактирования загружаем актуальную раскладку мест для выбранного тура
  useEffect(() => {
    if (editingTourId) {
      axios.get("http://127.0.0.1:8000/seat", {
        params: { tour_id: editingTourId, adminMode: 1 }
      })
      .then(res => setEditingTourSeats(res.data.seats))
      .catch(err => console.error("Ошибка загрузки мест для редактирования:", err));
    }
  }, [editingTourId]);

  const handleToggleSeatNew = (seatNum) => {
    setNewTour(prev => ({
      ...prev,
      activeSeats: prev.activeSeats.includes(seatNum)
        ? prev.activeSeats.filter(s => s !== seatNum)
        : [...prev.activeSeats, seatNum]
    }));
  };

  const handleCreateTour = (e) => {
    e.preventDefault();
    axios.post("http://127.0.0.1:8000/tours", {
      route_id: Number(newTour.route_id),
      pricelist_id: Number(newTour.pricelist_id),
      date: newTour.date,
      layout_variant: Number(newTour.layout_variant),
      active_seats: newTour.activeSeats
    })
    .then(() => {
      loadData();
      setNewTour({ route_id: "", pricelist_id: "", date: "", layout_variant: "", activeSeats: [] });
    })
    .catch(err => console.error("Ошибка создания тура:", err));
  };

  const handleDeleteTour = (tourId) => {
    axios.delete(`http://127.0.0.1:8000/tours/${tourId}`)
      .then(() => setTours(tours.filter(t => t.id !== tourId)))
      .catch(err => console.error("Ошибка удаления тура:", err));
  };

  const handleEditTour = (tour) => {
    setEditingTourId(tour.id);
    setEditingTourData({
      ...tour,
      layout_variant: String(tour.layout_variant || ""),
      activeSeats: [] // Если API не возвращает активные места, можно оставить пустым или подгрузить их отдельно
    });
  };

  const handleToggleSeatEdit = (seatNum) => {
    setEditingTourData(prev => ({
      ...prev,
      activeSeats: prev.activeSeats.includes(seatNum)
        ? prev.activeSeats.filter(s => s !== seatNum)
        : [...prev.activeSeats, seatNum]
    }));
  };

  const handleSaveEdit = (tourId) => {
    axios.put(`http://127.0.0.1:8000/tours/${tourId}`, {
      route_id: Number(editingTourData.route_id),
      pricelist_id: Number(editingTourData.pricelist_id),
      date: editingTourData.date,
      layout_variant: Number(editingTourData.layout_variant),
      active_seats: editingTourData.activeSeats
    })
    .then(() => {
      loadData();
      setEditingTourId(null);
      setEditingTourSeats([]);
    })
    .catch(err => console.error("Ошибка обновления тура:", err));
  };

  const handleCancelEdit = () => {
    setEditingTourId(null);
    setEditingTourData({ route_id: "", pricelist_id: "", date: "", layout_variant: "", activeSeats: [] });
    setEditingTourSeats([]);
  };

  return (
    <div className="container">
      <h2>Рейсы (Туры)</h2>
      <table className="styled-table">
        <thead>
          <tr>
            <th>Маршрут</th>
            <th>Прайс-лист</th>
            <th>Дата</th>
            <th>Раскладка</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {tours.map(tour => {
            const isEditing = (tour.id === editingTourId);
            return (
              <tr key={tour.id}>
                <td>
                  {isEditing ? (
                    <select
                      value={editingTourData.route_id}
                      onChange={(e) =>
                        setEditingTourData({ ...editingTourData, route_id: e.target.value })
                      }
                    >
                      <option value="">Маршрут</option>
                      {routes.map(r => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                  ) : (
                    routes.find(r => r.id === tour.route_id)?.name || tour.route_id
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <select
                      value={editingTourData.pricelist_id}
                      onChange={(e) =>
                        setEditingTourData({ ...editingTourData, pricelist_id: e.target.value })
                      }
                    >
                      <option value="">Прайс-лист</option>
                      {pricelists.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  ) : (
                    pricelists.find(p => p.id === tour.pricelist_id)?.name || tour.pricelist_id
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <input
                      type="date"
                      value={editingTourData.date}
                      onChange={(e) =>
                        setEditingTourData({ ...editingTourData, date: e.target.value })
                      }
                    />
                  ) : (
                    tour.date
                  )}
                </td>
                <td>
                  {isEditing ? (
                    <select
                      value={editingTourData.layout_variant}
                      onChange={(e) =>
                        setEditingTourData({ ...editingTourData, layout_variant: e.target.value, activeSeats: [] })
                      }
                    >
                      <option value="">(Не выбрано)</option>
                      <option value="1">Neoplan</option>
                      <option value="2">Travego</option>
                    </select>
                  ) : (
                    tour.layout_variant === 1 ? "Neoplan" : "Travego"
                  )}
                </td>
                <td className="actions-cell">
                  {isEditing ? (
                    <>
                      <button className="icon-btn" onClick={() => handleSaveEdit(tour.id)}>
                        <img src={saveIcon} alt="Сохранить" />
                      </button>
                      <button className="icon-btn" onClick={handleCancelEdit}>
                        <img src={cancelIcon} alt="Отменить" />
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="icon-btn" onClick={() => handleEditTour(tour)}>
                        <img src={editIcon} alt="Редактировать" />
                      </button>
                      <button className="icon-btn" onClick={() => handleDeleteTour(tour.id)}>
                        <img src={deleteIcon} alt="Удалить" />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {editingTourId && editingTourData.layout_variant && (
        <div style={{ marginTop: "20px" }}>
          <h4>Редактирование мест</h4>
          {editingTourData.layout_variant === "1" ? (
            <BusLayoutNeoplan
              selectedSeats={editingTourData.activeSeats}
              seats={editingTourSeats}
              toggleSeat={(seatNum) => handleToggleSeatEdit(seatNum)}
              interactive={true}
            />
          ) : (
            <BusLayoutTravego
              selectedSeats={editingTourData.activeSeats}
              seats={editingTourSeats}
              toggleSeat={(seatNum) => handleToggleSeatEdit(seatNum)}
              interactive={true}
            />
          )}
        </div>
      )}

      <h3 style={{ marginTop: "40px" }}>Создать новый рейс</h3>
      <form onSubmit={handleCreateTour} style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
        <select
          required
          value={newTour.route_id}
          onChange={(e) => setNewTour({ ...newTour, route_id: e.target.value })}
        >
          <option value="">Маршрут</option>
          {routes.map(r => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>

        <select
          required
          value={newTour.pricelist_id}
          onChange={(e) => setNewTour({ ...newTour, pricelist_id: e.target.value })}
        >
          <option value="">Прайс-лист</option>
          {pricelists.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <input
          required
          type="date"
          value={newTour.date}
          onChange={(e) => setNewTour({ ...newTour, date: e.target.value })}
        />

        <select
          value={newTour.layout_variant}
          onChange={(e) =>
            setNewTour({ ...newTour, layout_variant: e.target.value, activeSeats: [] })
          }
        >
          <option value="">(Не выбрано)</option>
          <option value="1">Neoplan</option>
          <option value="2">Travego</option>
        </select>

        {newTour.layout_variant && (
          <div style={{ flexBasis: "100%" }}>
            {newTour.layout_variant === "1" ? (
              <BusLayoutNeoplan
                selectedSeats={newTour.activeSeats}
                seats={[]}  // Если нет отдельного API – оставляем пустым
                toggleSeat={(seatNum) =>
                  setNewTour(prev => ({
                    ...prev,
                    activeSeats: prev.activeSeats.includes(seatNum)
                      ? prev.activeSeats.filter(s => s !== seatNum)
                      : [...prev.activeSeats, seatNum]
                  }))
                }
                interactive={true}
              />
            ) : (
              <BusLayoutTravego
                selectedSeats={newTour.activeSeats}
                seats={[]}  // Аналогично
                toggleSeat={(seatNum) =>
                  setNewTour(prev => ({
                    ...prev,
                    activeSeats: prev.activeSeats.includes(seatNum)
                      ? prev.activeSeats.filter(s => s !== seatNum)
                      : [...prev.activeSeats, seatNum]
                  }))
                }
                interactive={true}
              />
            )}
          </div>
        )}

        <button type="submit" style={{ marginTop: "10px" }}>
          Создать рейс
        </button>
      </form>
    </div>
  );
}

export default ToursPage;
