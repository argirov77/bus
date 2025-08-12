import React, { useState, useEffect } from "react";
import axios from "axios";
import IconButton from "../components/IconButton";
import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import addIcon from "../assets/icons/add.png";
import saveIcon from "../assets/icons/save.png";
import cancelIcon from "../assets/icons/cancel.png";

import { API } from "../config";

function PricelistPage() {
  const [pricelists, setPricelists] = useState([]);
  const [selectedPricelist, setSelectedPricelist] = useState(null);
  const [prices, setPrices] = useState([]);
  const [newPrice, setNewPrice] = useState({ departure_stop_id: "", arrival_stop_id: "", price: "" });
  const [stops, setStops] = useState([]);
  const [editingPriceId, setEditingPriceId] = useState(null);
  const [editingPriceData, setEditingPriceData] = useState({ price: "" });

  // Для создания и редактирования прайс-листов
  const [newPricelistName, setNewPricelistName] = useState("");
  const [editingPricelistId, setEditingPricelistId] = useState(null);
  const [editingPricelistName, setEditingPricelistName] = useState("");

  const [activePricelistId, setActivePricelistId] = useState(null);

  // Демо статус прайс-листов более не используется

  useEffect(() => {
    fetchPricelists();
    axios.get(`${API}/stops`)
      .then(res => setStops(res.data))
      .catch(err => console.error(err));
    axios.get(`${API}/admin/selected_pricelist`)
      .then(res => setActivePricelistId(res.data.pricelist.id))
      .catch(err => console.error(err));
  }, []);

  const fetchPricelists = () => {
    axios.get(`${API}/pricelists`)
      .then(res => setPricelists(res.data))
      .catch(err => console.error(err));
  };

  useEffect(() => {
    if (selectedPricelist) {
      axios.get(`${API}/prices?pricelist_id=${selectedPricelist.id}`)
        .then(res => setPrices(res.data))
        .catch(err => console.error(err));
    } else {
      setPrices([]);
    }
  }, [selectedPricelist]);

  const handleSelectPricelist = (pl) => {
    setSelectedPricelist(pl);
    setEditingPriceId(null);
  };

  // Создание нового прайс-листа
  const handleCreatePricelist = (e) => {
    e.preventDefault();
    if (!newPricelistName.trim()) return;
    axios.post(`${API}/pricelists`, { name: newPricelistName.trim() })
      .then(res => {
        setPricelists([...pricelists, res.data]);
        setNewPricelistName("");
      })
      .catch(err => console.error(err));
  };

  // Начать редактирование существующего прайс-листа
  const handleEditPricelist = (pl) => {
    setEditingPricelistId(pl.id);
    setEditingPricelistName(pl.name);
  };

  // Отмена редактирования прайс-листа
  const handleCancelEditPricelist = () => {
    setEditingPricelistId(null);
    setEditingPricelistName("");
  };

  // Сохранить изменения в прайс-листе
  const handleUpdatePricelist = (e) => {
    e.preventDefault();
    axios.put(`${API}/pricelists/${editingPricelistId}`, { name: editingPricelistName.trim() })
      .then(res => {
        setPricelists(pricelists.map(pl => pl.id === editingPricelistId ? res.data : pl));
        // Переселектить, если редактируемый прайс-лист активен
        if (selectedPricelist?.id === editingPricelistId) {
          setSelectedPricelist(res.data);
        }
        handleCancelEditPricelist();
      })
      .catch(err => console.error(err));
  };

  const handleSetActivePricelist = (id) => {
    setActivePricelistId(id);
    axios.post(`${API}/admin/selected_pricelist`, { pricelist_id: id })
      .catch(err => console.error(err));
  };

  // Удалить прайс-лист
  const handleDeletePricelist = (id) => {
    axios.delete(`${API}/pricelists/${id}`)
      .then(() => {
        setPricelists(pricelists.filter(pl => pl.id !== id));
        if (selectedPricelist?.id === id) {
          setSelectedPricelist(null);
        }
      })
      .catch(err => console.error(err));
  };

  // Остальные хэндлеры работы с ценами
  const handleCreatePrice = (e) => {
    e.preventDefault();
    axios.post(`${API}/prices`, {
      pricelist_id: selectedPricelist.id,
      departure_stop_id: Number(newPrice.departure_stop_id),
      arrival_stop_id: Number(newPrice.arrival_stop_id),
      price: Number(newPrice.price)
    }).then(res => {
      setPrices([...prices, res.data]);
      setNewPrice({ departure_stop_id: "", arrival_stop_id: "", price: "" });
    });
  };

  const handleDeletePrice = (priceId) => {
    axios.delete(`${API}/prices/${priceId}`)
      .then(() => setPrices(prices.filter(p => p.id !== priceId)));
  };

  const handleEditPrice = (priceObj) => {
    setEditingPriceId(priceObj.id);
    setEditingPriceData({ price: priceObj.price.toString() });
  };

  const handleUpdatePrice = (e) => {
    e.preventDefault();
    const updated = { ...prices.find(p => p.id === editingPriceId), price: Number(editingPriceData.price) };
    axios.put(`${API}/prices/${editingPriceId}`, updated)
      .then(res => {
        setPrices(prices.map(p => p.id === editingPriceId ? res.data : p));
        setEditingPriceId(null);
      });
  };

  return (
    <div className="container">
      <h2>Прайс-листы</h2>

      {/* Форма для добавления нового прайс-листа */}
      <form onSubmit={handleCreatePricelist} className="add-pricelist-form">
        <input
          type="text"
          placeholder="Название нового прайс-листа"
          value={newPricelistName}
          onChange={e => setNewPricelistName(e.target.value)}
          required
        />
        <IconButton type="submit" icon={addIcon} alt="Добавить прайс-лист" className="btn--primary" />
      </form>

      <div className="routes-wrapper">
        {pricelists.map(pl => (
          <div key={pl.id} className="pricelist-item">
            {editingPricelistId === pl.id ? (
              <form onSubmit={handleUpdatePricelist} className="edit-pricelist-form">
                <input
                  type="text"
                  value={editingPricelistName}
                  onChange={e => setEditingPricelistName(e.target.value)}
                  required
                />
                <IconButton type="submit" icon={saveIcon} alt="Сохранить" />
                <IconButton type="button" onClick={handleCancelEditPricelist} icon={cancelIcon} alt="Отмена" />
              </form>
            ) : (
              <>
                <button
                  className={`btn btn--sm ${selectedPricelist?.id === pl.id ? "btn--primary" : "btn--ghost"}`}
                  onClick={() => handleSelectPricelist(pl)}
                >
                  {pl.name}
                </button>
                <label style={{ marginLeft: '4px' }}>
                  <input
                    type="radio"
                    name="activePricelist"
                    checked={activePricelistId === pl.id}
                    onChange={() => handleSetActivePricelist(pl.id)}
                  />
                  active
                </label>
                <IconButton className="btn--ghost" onClick={() => handleEditPricelist(pl)} icon={editIcon} alt="Редактировать прайс-лист" />
                <IconButton className="btn--danger" onClick={() => handleDeletePricelist(pl.id)} icon={deleteIcon} alt="Удалить прайс-лист" />
              </>
            )}
          </div>
        ))}
      </div>

      {selectedPricelist && (
        <>
          <h3>Цены для: {selectedPricelist.name}</h3>

          <table className="styled-table">
            <thead>
              <tr>
                <th>От остановки</th>
                <th>До остановки</th>
                <th>Цена</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {prices.map(p => (
                <tr key={p.id}>
                  <td>{p.departure_stop_name || `ID: ${p.departure_stop_id}`}</td>
                  <td>{p.arrival_stop_name || `ID: ${p.arrival_stop_id}`}</td>
                  <td>
                    {editingPriceId === p.id ? (
                      <input
                        type="number"
                        value={editingPriceData.price}
                        onChange={e => setEditingPriceData({ price: e.target.value })}
                      />
                    ) : (
                      p.price
                    )}
                  </td>
                  <td className="actions-cell">
                    {editingPriceId === p.id ? (
                      <>
                        <IconButton onClick={handleUpdatePrice} icon={saveIcon} alt="Сохранить" />
                        <IconButton onClick={() => setEditingPriceId(null)} icon={cancelIcon} alt="Отмена" />
                      </>
                    ) : (
                      <>
                        <IconButton className="btn--ghost" onClick={() => handleEditPrice(p)} icon={editIcon} alt="Редактировать цену" />
                        <IconButton className="btn--danger" onClick={() => handleDeletePrice(p.id)} icon={deleteIcon} alt="Удалить цену" />
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4>Добавить новую цену</h4>
          <form onSubmit={handleCreatePrice} className="add-price-form">
            <select
              required
              value={newPrice.departure_stop_id}
              onChange={e => setNewPrice({ ...newPrice, departure_stop_id: e.target.value })}
            >
              <option value="">Отправление</option>
              {stops.map(s => <option key={s.id} value={s.id}>{s.stop_name}</option>)}
            </select>

            <select
              required
              value={newPrice.arrival_stop_id}
              onChange={e => setNewPrice({ ...newPrice, arrival_stop_id: e.target.value })}
            >
              <option value="">Прибытие</option>
              {stops.map(s => <option key={s.id} value={s.id}>{s.stop_name}</option>)}
            </select>

            <input
              required
              type="number"
              placeholder="Цена"
              value={newPrice.price}
              onChange={e => setNewPrice({ ...newPrice, price: e.target.value })}
            />

            <IconButton type="submit" icon={addIcon} alt="Добавить цену" className="btn--primary" />
          </form>
        </>
      )}
    </div>
  );
}

export default PricelistPage;
