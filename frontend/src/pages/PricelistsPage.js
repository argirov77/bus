import React, { useState, useEffect } from "react";
import axios from "axios";
import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
// Добавляем импорт иконки "add"
import addIcon from "../assets/icons/add.png";

function PricelistPage() {
  const [pricelists, setPricelists] = useState([]);
  const [selectedPricelist, setSelectedPricelist] = useState(null);
  const [prices, setPrices] = useState([]);
  const [newPrice, setNewPrice] = useState({ departure_stop_id: "", arrival_stop_id: "", price: "" });
  const [stops, setStops] = useState([]);
  const [editingPriceId, setEditingPriceId] = useState(null);
  const [editingPriceData, setEditingPriceData] = useState({ price: "" });

  useEffect(() => {
    axios.get("http://127.0.0.1:8000/pricelists").then(res => setPricelists(res.data));
    axios.get("http://127.0.0.1:8000/stops").then(res => setStops(res.data));
  }, []);

  useEffect(() => {
    if (selectedPricelist) {
      axios.get(`http://127.0.0.1:8000/prices?pricelist_id=${selectedPricelist.id}`)
        .then(res => setPrices(res.data));
    } else {
      setPrices([]);
    }
  }, [selectedPricelist]);

  const handleSelectPricelist = (pl) => setSelectedPricelist(pl);

  const handleCreatePrice = (e) => {
    e.preventDefault();
    axios.post("http://127.0.0.1:8000/prices", {
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
    axios.delete(`http://127.0.0.1:8000/prices/${priceId}`)
      .then(() => setPrices(prices.filter(p => p.id !== priceId)));
  };

  const handleEditPrice = (priceObj) => {
    setEditingPriceId(priceObj.id);
    setEditingPriceData({ price: priceObj.price.toString() });
  };

  const handleUpdatePrice = (e) => {
    e.preventDefault();
    axios.put(`http://127.0.0.1:8000/prices/${editingPriceId}`, {
      ...prices.find(p => p.id === editingPriceId),
      price: Number(editingPriceData.price)
    }).then(res => {
      setPrices(prices.map(p => p.id === editingPriceId ? res.data : p));
      setEditingPriceId(null);
    });
  };

  return (
    <div className="container">
      <h2>Прайс-листы</h2>

      <div className="routes-wrapper">
        {pricelists.map(pl => (
          <button
            key={pl.id}
            className={`route-btn ${selectedPricelist?.id === pl.id ? "active" : ""}`}
            onClick={() => handleSelectPricelist(pl)}
          >
            {pl.name}
          </button>
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
                        <button onClick={handleUpdatePrice}>✅</button>
                        <button onClick={() => setEditingPriceId(null)}>❌</button>
                      </>
                    ) : (
                      <>
                        <button className="icon-btn" onClick={() => handleEditPrice(p)}>
                          <img src={editIcon} alt="Редактировать" />
                        </button>
                        <button className="icon-btn" onClick={() => handleDeletePrice(p.id)}>
                          <img src={deleteIcon} alt="Удалить" />
                        </button>
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

            <button type="submit" className="icon-btn add-btn">
              <img src={addIcon} alt="Добавить цену" />
            </button>
          </form>
        </>
      )}
    </div>
  );
}

export default PricelistPage;
