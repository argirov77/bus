import React, { useState, useEffect } from "react";
import axios from "axios";

import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import addIcon from "../assets/icons/add.png";
import saveIcon from "../assets/icons/save.png";
import cancelIcon from "../assets/icons/cancel.png";

export default function TourPage() {
  const [tours, setTours] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [pricelists, setPricelists] = useState([]);

  const [newTour, setNewTour] = useState({
    route_id: "",
    pricelist_id: "",
    date: "",
    seats: "",
  });

  const [editingTourId, setEditingTourId] = useState(null);
  const [editingTourData, setEditingTourData] = useState({});

  useEffect(() => {
    loadData();
  }, []);

  const loadData = () => {
    axios.get("http://127.0.0.1:8000/tours").then((res) => setTours(res.data));
    axios.get("http://127.0.0.1:8000/routes").then((res) => setRoutes(res.data));
    axios.get("http://127.0.0.1:8000/pricelists").then((res) => setPricelists(res.data));
  };

  const handleCreateTour = (e) => {
    e.preventDefault();
    axios
      .post("http://127.0.0.1:8000/tours", {
        route_id: Number(newTour.route_id),
        pricelist_id: Number(newTour.pricelist_id),
        date: newTour.date,
        seats: Number(newTour.seats),
      })
      .then((res) => {
        loadData();
        setNewTour({ route_id: "", pricelist_id: "", date: "", seats: "" });
      });
  };

  const handleDeleteTour = (tourId) => {
    axios.delete(`http://127.0.0.1:8000/tours/${tourId}`).then(() => {
      setTours(tours.filter((t) => t.id !== tourId));
    });
  };

  const handleEditTour = (tour) => {
    setEditingTourId(tour.id);
    setEditingTourData({ ...tour });
  };

  const handleSaveEdit = (tourId) => {
    axios
      .put(`http://127.0.0.1:8000/tours/${tourId}`, editingTourData)
      .then(() => {
        loadData();
        setEditingTourId(null);
      });
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
            <th>Места</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {tours.map((tour) => (
            <tr key={tour.id}>
              <td>
                {editingTourId === tour.id ? (
                  <select
                    value={editingTourData.route_id}
                    onChange={(e) =>
                      setEditingTourData({ ...editingTourData, route_id: Number(e.target.value) })
                    }
                  >
                    {routes.map((r) => (
                      <option key={r.id} value={r.id}>{r.name}</option>
                    ))}
                  </select>
                ) : (
                  routes.find((r) => r.id === tour.route_id)?.name || tour.route_id
                )}
              </td>

              <td>
                {editingTourId === tour.id ? (
                  <select
                    value={editingTourData.pricelist_id}
                    onChange={(e) =>
                      setEditingTourData({ ...editingTourData, pricelist_id: Number(e.target.value) })
                    }
                  >
                    {pricelists.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                ) : (
                  pricelists.find((p) => p.id === tour.pricelist_id)?.name || tour.pricelist_id
                )}
              </td>

              <td>
                {editingTourId === tour.id ? (
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
                {editingTourId === tour.id ? (
                  <input
                    type="number"
                    value={editingTourData.seats}
                    onChange={(e) =>
                      setEditingTourData({ ...editingTourData, seats: Number(e.target.value) })
                    }
                  />
                ) : (
                  tour.seats
                )}
              </td>

              <td className="actions-cell">
                {editingTourId === tour.id ? (
                  <>
                    <button className="icon-btn" onClick={() => handleSaveEdit(tour.id)}>
                      <img src={saveIcon} alt="Сохранить" />
                    </button>
                    <button className="icon-btn" onClick={() => setEditingTourId(null)}>
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
          ))}
        </tbody>
      </table>

      <h3>Создать новый рейс</h3>
      <form onSubmit={handleCreateTour} className="add-price-form">
        <select required value={newTour.route_id} onChange={(e) => setNewTour({ ...newTour, route_id: e.target.value })}>
          <option value="">Маршрут</option>
          {routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>

        <select required value={newTour.pricelist_id} onChange={(e) => setNewTour({ ...newTour, pricelist_id: e.target.value })}>
          <option value="">Прайс-лист</option>
          {pricelists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <input required type="date" value={newTour.date} onChange={(e) => setNewTour({ ...newTour, date: e.target.value })}/>
        <input required type="number" placeholder="Места" value={newTour.seats} onChange={(e) => setNewTour({ ...newTour, seats: e.target.value })}/>

        <button type="submit" className="icon-btn add-btn">
          <img src={addIcon} alt="Добавить рейс" />
        </button>
      </form>
    </div>
  );
}
