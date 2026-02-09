import React, { useState, useEffect, useMemo, useCallback } from "react";
import axios from "axios";
import IconButton from "../components/IconButton";
import editIcon from "../assets/icons/edit.png";
import deleteIcon from "../assets/icons/delete.png";
import addIcon from "../assets/icons/add.png";
import saveIcon from "../assets/icons/save.png";
import cancelIcon from "../assets/icons/cancel.png";

import { API } from "../config";

const makeCellKey = (depId, arrId) => `${depId}:${arrId}`;

const normalizeMoney = (rawValue) => {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return { value: null, error: null };
  }
  const normalized = trimmed.replace(",", ".");
  const numeric = Number(normalized);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return { value: null, error: "Цена должна быть числом больше 0" };
  }
  return { value: numeric, error: null };
};

const getValidationError = (rawValue) => {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return "";
  }
  const numeric = Number(trimmed.replace(",", "."));
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return "Цена должна быть числом больше 0";
  }
  return "";
};

const PriceMatrixCell = React.memo(function PriceMatrixCell({ cell, currency, onChange }) {
  const cellClassName = [
    "price-matrix__cell",
    cell.disabled ? "price-matrix__cell--disabled" : "",
    cell.dirty ? "price-matrix__cell--dirty" : "",
    cell.error ? "price-matrix__cell--error" : "",
    cell.priceId && cell.value === "" && cell.dirty ? "price-matrix__cell--deleted" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <td className={cellClassName}>
      <input
        className="price-matrix__input"
        type="text"
        inputMode="decimal"
        placeholder={cell.disabled ? "—" : ""}
        disabled={cell.disabled}
        value={cell.value}
        onChange={(event) => onChange(cell.cellKey, event.target.value)}
      />
      {cell.priceId && cell.value === "" && cell.dirty && (
        <span className="price-matrix__cell-status">будет удалено</span>
      )}
      {cell.error && <span className="price-matrix__cell-error">{cell.error}</span>}
      {!cell.error && cell.value !== "" && currency && (
        <span className="price-matrix__cell-currency">{currency}</span>
      )}
    </td>
  );
});

function PricelistPage() {
  const [pricelists, setPricelists] = useState([]);
  const [selectedPricelist, setSelectedPricelist] = useState(null);
  const [prices, setPrices] = useState([]);
  const [stops, setStops] = useState([]);
  const [gridMap, setGridMap] = useState({});
  const [pricesSnapshotMap, setPricesSnapshotMap] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [saveErrors, setSaveErrors] = useState([]);
  const [isMatrixLoading, setIsMatrixLoading] = useState(false);
  const [addStopOpen, setAddStopOpen] = useState(false);
  const [newStopName, setNewStopName] = useState("");

  // Для создания и редактирования прайс-листов
  const [newPricelistName, setNewPricelistName] = useState("");
  const [newPricelistCurrency, setNewPricelistCurrency] = useState("UAH");
  const [editingPricelistId, setEditingPricelistId] = useState(null);
  const [editingPricelistName, setEditingPricelistName] = useState("");
  const [editingPricelistCurrency, setEditingPricelistCurrency] = useState("UAH");

  const [activePricelistId, setActivePricelistId] = useState(null);

  useEffect(() => {
    fetchPricelists();
    axios
      .get(`${API}/admin/selected_pricelist`)
      .then((res) => setActivePricelistId(res.data.pricelist.id))
      .catch((err) => console.error(err));
  }, []);

  const fetchPricelists = () => {
    axios
      .get(`${API}/pricelists`)
      .then((res) => setPricelists(res.data))
      .catch((err) => console.error(err));
  };

  const buildGrid = useCallback((stopsList, pricesList) => {
    const priceMap = {};
    const snapshotMap = {};
    pricesList.forEach((price) => {
      const key = makeCellKey(price.departure_stop_id, price.arrival_stop_id);
      priceMap[key] = price;
      snapshotMap[key] = { priceId: price.id, amount: price.price };
    });

    const nextGridMap = {};
    stopsList.forEach((departure) => {
      stopsList.forEach((arrival) => {
        const cellKey = makeCellKey(departure.id, arrival.id);
        const existingPrice = priceMap[cellKey];
        const originalValue = existingPrice ? String(existingPrice.price) : "";
        nextGridMap[cellKey] = {
          cellKey,
          depId: departure.id,
          arrId: arrival.id,
          value: originalValue,
          originalValue,
          priceId: existingPrice?.id,
          disabled: departure.id === arrival.id,
          dirty: false,
          error: "",
        };
      });
    });

    return { nextGridMap, snapshotMap };
  }, []);

  const fetchMatrixData = useCallback(
    async (pricelistId) => {
      setIsMatrixLoading(true);
      try {
        const [stopsRes, pricesRes] = await Promise.all([
          axios.get(`${API}/stops`),
          axios.get(`${API}/prices?pricelist_id=${pricelistId}`),
        ]);
        setStops(stopsRes.data);
        setPrices(pricesRes.data);
        const { nextGridMap, snapshotMap } = buildGrid(stopsRes.data, pricesRes.data);
        setGridMap(nextGridMap);
        setPricesSnapshotMap(snapshotMap);
        setSaveMessage("");
        setSaveErrors([]);
      } catch (err) {
        console.error(err);
      } finally {
        setIsMatrixLoading(false);
      }
    },
    [buildGrid]
  );

  useEffect(() => {
    if (selectedPricelist) {
      fetchMatrixData(selectedPricelist.id);
    } else {
      setPrices([]);
      setStops([]);
      setGridMap({});
      setPricesSnapshotMap({});
    }
  }, [selectedPricelist, fetchMatrixData]);

  const handleSelectPricelist = (pl) => {
    setSelectedPricelist(pl);
  };

  // Создание нового прайс-листа
  const handleCreatePricelist = (e) => {
    e.preventDefault();
    if (!newPricelistName.trim()) return;
    const payload = {
      name: newPricelistName.trim(),
      currency: newPricelistCurrency.trim() || "UAH",
    };
    axios
      .post(`${API}/pricelists`, payload)
      .then((res) => {
        setPricelists([...pricelists, res.data]);
        setNewPricelistName("");
        setNewPricelistCurrency("UAH");
      })
      .catch((err) => console.error(err));
  };

  // Начать редактирование существующего прайс-листа
  const handleEditPricelist = (pl) => {
    setEditingPricelistId(pl.id);
    setEditingPricelistName(pl.name);
    setEditingPricelistCurrency(pl.currency || "UAH");
  };

  // Отмена редактирования прайс-листа
  const handleCancelEditPricelist = () => {
    setEditingPricelistId(null);
    setEditingPricelistName("");
    setEditingPricelistCurrency("UAH");
  };

  // Сохранить изменения в прайс-листе
  const handleUpdatePricelist = (e) => {
    e.preventDefault();
    const payload = {
      name: editingPricelistName.trim(),
      currency: editingPricelistCurrency.trim() || "UAH",
    };
    axios
      .put(`${API}/pricelists/${editingPricelistId}`, payload)
      .then((res) => {
        setPricelists(pricelists.map((pl) => (pl.id === editingPricelistId ? res.data : pl)));
        if (selectedPricelist?.id === editingPricelistId) {
          setSelectedPricelist(res.data);
        }
        handleCancelEditPricelist();
      })
      .catch((err) => console.error(err));
  };

  const handleSetActivePricelist = (id) => {
    setActivePricelistId(id);
    axios.post(`${API}/admin/selected_pricelist`, { pricelist_id: id }).catch((err) => console.error(err));
  };

  // Удалить прайс-лист
  const handleDeletePricelist = (id) => {
    axios
      .delete(`${API}/pricelists/${id}`)
      .then(() => {
        setPricelists(pricelists.filter((pl) => pl.id !== id));
        if (selectedPricelist?.id === id) {
          setSelectedPricelist(null);
        }
      })
      .catch((err) => console.error(err));
  };

  const handleCellChange = useCallback((cellKey, nextValue) => {
    setGridMap((prev) => {
      const current = prev[cellKey];
      if (!current) {
        return prev;
      }
      const error = getValidationError(nextValue);
      return {
        ...prev,
        [cellKey]: {
          ...current,
          value: nextValue,
          dirty: nextValue !== current.originalValue,
          error,
        },
      };
    });
  }, []);

  const handleResetGrid = () => {
    if (!selectedPricelist) return;
    const { nextGridMap, snapshotMap } = buildGrid(stops, prices);
    setGridMap(nextGridMap);
    setPricesSnapshotMap(snapshotMap);
    setSaveErrors([]);
    setSaveMessage("");
  };

  const handleSave = async () => {
    if (!selectedPricelist || isSaving) return;
    setIsSaving(true);
    setSaveErrors([]);
    setSaveMessage("");

    const cells = Object.values(gridMap);
    const nextGridMap = { ...gridMap };
    const toDelete = [];
    const toCreate = [];
    const toUpdate = [];
    const validationErrors = [];

    cells.forEach((cell) => {
      if (!cell.dirty || cell.disabled) {
        return;
      }
      const { value: normalized, error } = normalizeMoney(cell.value);
      if (error) {
        validationErrors.push(`${cell.depId} → ${cell.arrId}: ${error}`);
        nextGridMap[cell.cellKey] = { ...cell, error };
        return;
      }
      nextGridMap[cell.cellKey] = { ...cell, error: "" };

      if (normalized === null) {
        if (cell.priceId) {
          toDelete.push(cell);
        }
        return;
      }

      if (!cell.priceId) {
        toCreate.push({ ...cell, amount: normalized });
        return;
      }

      const snapshot = pricesSnapshotMap[cell.cellKey];
      if (!snapshot || snapshot.amount !== normalized) {
        toUpdate.push({ ...cell, amount: normalized });
      }
    });

    setGridMap(nextGridMap);

    if (validationErrors.length > 0) {
      setSaveErrors(validationErrors);
      setIsSaving(false);
      return;
    }

    const operationErrors = [];

    const handleRequestError = (cell, errorMessage) => {
      operationErrors.push(errorMessage);
      setGridMap((prev) => ({
        ...prev,
        [cell.cellKey]: {
          ...prev[cell.cellKey],
          error: "Ошибка сохранения",
        },
      }));
    };

    try {
      if (toDelete.length > 0) {
        await Promise.all(
          toDelete.map((cell) =>
            axios.delete(`${API}/prices/${cell.priceId}`).catch((error) => {
              handleRequestError(cell, `Удаление: ${error.message}`);
            })
          )
        );
      }

      if (toUpdate.length > 0) {
        await Promise.all(
          toUpdate.map((cell) =>
            axios
              .put(`${API}/prices/${cell.priceId}`, {
                pricelist_id: selectedPricelist.id,
                departure_stop_id: cell.depId,
                arrival_stop_id: cell.arrId,
                price: cell.amount,
              })
              .catch((error) => {
                handleRequestError(cell, `Обновление: ${error.message}`);
              })
          )
        );
      }

      if (toCreate.length > 0) {
        let refreshedPrices = null;
        for (const cell of toCreate) {
          try {
            await axios.post(`${API}/prices`, {
              pricelist_id: selectedPricelist.id,
              departure_stop_id: cell.depId,
              arrival_stop_id: cell.arrId,
              price: cell.amount,
            });
          } catch (error) {
            const status = error.response?.status;
            const detail = String(error.response?.data?.detail || error.message || "");
            const isConflict = status === 409 || detail.toLowerCase().includes("duplicate");
            if (isConflict) {
              if (!refreshedPrices) {
                const refreshRes = await axios.get(`${API}/prices?pricelist_id=${selectedPricelist.id}`);
                refreshedPrices = refreshRes.data;
              }
              const existing = refreshedPrices.find(
                (price) => price.departure_stop_id === cell.depId && price.arrival_stop_id === cell.arrId
              );
              if (existing) {
                try {
                  await axios.put(`${API}/prices/${existing.id}`, {
                    pricelist_id: selectedPricelist.id,
                    departure_stop_id: cell.depId,
                    arrival_stop_id: cell.arrId,
                    price: cell.amount,
                  });
                } catch (updateError) {
                  handleRequestError(cell, `Конфликт create/update: ${updateError.message}`);
                }
              } else {
                handleRequestError(cell, `Конфликт create: ${detail}`);
              }
            } else {
              handleRequestError(cell, `Создание: ${error.message}`);
            }
          }
        }
      }
    } catch (error) {
      operationErrors.push(error.message);
    }

    if (operationErrors.length > 0) {
      setSaveErrors(operationErrors);
      setIsSaving(false);
      return;
    }

    await fetchMatrixData(selectedPricelist.id);
    setSaveMessage("Сохранено");
    setIsSaving(false);
  };

  const handleAddStop = async (event) => {
    event.preventDefault();
    if (!selectedPricelist || !newStopName.trim()) return;
    try {
      await axios.post(`${API}/stops`, { stop_name: newStopName.trim() });
      setAddStopOpen(false);
      setNewStopName("");
      await fetchMatrixData(selectedPricelist.id);
    } catch (error) {
      console.error(error);
    }
  };

  const hasChanges = useMemo(
    () => Object.values(gridMap).some((cell) => cell.dirty),
    [gridMap]
  );

  const gridRows = useMemo(
    () =>
      stops.map((arrivalStop) => ({
        arrivalStop,
        cells: stops.map((departureStop) =>
          gridMap[makeCellKey(departureStop.id, arrivalStop.id)]
        ),
      })),
    [stops, gridMap]
  );

  return (
    <div className="container">
      <h2>Прайс-листы</h2>

      {/* Форма для добавления нового прайс-листа */}
      <form onSubmit={handleCreatePricelist} className="add-pricelist-form">
        <input
          type="text"
          placeholder="Название нового прайс-листа"
          value={newPricelistName}
          onChange={(e) => setNewPricelistName(e.target.value)}
          required
        />
        <input
          type="text"
          placeholder="Валюта"
          value={newPricelistCurrency}
          onChange={(e) => setNewPricelistCurrency(e.target.value)}
        />
        <IconButton type="submit" icon={addIcon} alt="Добавить прайс-лист" className="btn--primary" />
      </form>

      <div className="routes-wrapper">
        {pricelists.map((pl) => (
          <div key={pl.id} className="pricelist-item">
            {editingPricelistId === pl.id ? (
              <form onSubmit={handleUpdatePricelist} className="edit-pricelist-form">
                <input
                  type="text"
                  value={editingPricelistName}
                  onChange={(e) => setEditingPricelistName(e.target.value)}
                  required
                />
                <input
                  type="text"
                  value={editingPricelistCurrency}
                  onChange={(e) => setEditingPricelistCurrency(e.target.value)}
                  placeholder="Валюта"
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
                  {pl.name} ({pl.currency || "UAH"})
                </button>
                <label style={{ marginLeft: "4px" }}>
                  <input
                    type="radio"
                    name="activePricelist"
                    checked={activePricelistId === pl.id}
                    onChange={() => handleSetActivePricelist(pl.id)}
                  />
                  active
                </label>
                <IconButton
                  className="btn--ghost"
                  onClick={() => handleEditPricelist(pl)}
                  icon={editIcon}
                  alt="Редактировать прайс-лист"
                />
                <IconButton
                  className="btn--danger"
                  onClick={() => handleDeletePricelist(pl.id)}
                  icon={deleteIcon}
                  alt="Удалить прайс-лист"
                />
              </>
            )}
          </div>
        ))}
      </div>

      {selectedPricelist && (
        <>
          <div className="matrix-header">
            <div>
              <h3>
                Цены для: {selectedPricelist.name} ({selectedPricelist.currency || "UAH"})
              </h3>
              <p className="matrix-subtitle">
                Заполните значения для направлений. Пустая ячейка означает, что маршрута нет.
              </p>
            </div>
            <div className="matrix-actions">
              <IconButton
                className="btn--ghost"
                onClick={() => setAddStopOpen(true)}
                icon={addIcon}
                alt="Добавить остановку"
              />
              <IconButton
                className="btn--primary"
                onClick={handleSave}
                icon={saveIcon}
                alt="Сохранить изменения"
                disabled={!hasChanges || isSaving}
              />
              <IconButton
                className="btn--ghost"
                onClick={handleResetGrid}
                icon={cancelIcon}
                alt="Сбросить изменения"
                disabled={!hasChanges || isSaving}
              />
            </div>
          </div>

          {saveMessage && <div className="matrix-status matrix-status--success">{saveMessage}</div>}
          {saveErrors.length > 0 && (
            <div className="matrix-status matrix-status--error">
              <strong>Ошибки при сохранении:</strong>
              <ul>
                {saveErrors.map((error, index) => (
                  <li key={`${error}-${index}`}>{error}</li>
                ))}
              </ul>
            </div>
          )}

          {isMatrixLoading ? (
            <div className="matrix-status">Загрузка матрицы...</div>
          ) : (
            <div className="price-matrix-wrapper">
              <table className="price-matrix">
                <thead>
                  <tr>
                    <th className="price-matrix__corner">Прибытие \ Отправление</th>
                    {stops.map((departure) => (
                      <th key={departure.id} className="price-matrix__col-header">
                        {departure.stop_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {gridRows.map((row) => (
                    <tr key={row.arrivalStop.id}>
                      <th className="price-matrix__row-header">{row.arrivalStop.stop_name}</th>
                      {row.cells.map((cell) => (
                        <PriceMatrixCell
                          key={cell.cellKey}
                          cell={cell}
                          currency={selectedPricelist.currency || "UAH"}
                          onChange={handleCellChange}
                        />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {addStopOpen && (
        <div className="modal-overlay" onClick={() => setAddStopOpen(false)}>
          <div className="modal-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="modal-sheet__header">
              <div>
                <h3>Добавить остановку</h3>
                <p className="modal-sheet__subtitle">Новая остановка появится в матрице цен.</p>
              </div>
              <IconButton icon={cancelIcon} alt="Закрыть" onClick={() => setAddStopOpen(false)} />
            </div>
            <form className="modal-section" onSubmit={handleAddStop}>
              <label className="modal-field">
                Название остановки
                <input
                  type="text"
                  value={newStopName}
                  onChange={(event) => setNewStopName(event.target.value)}
                  placeholder="Введите название"
                  required
                />
              </label>
              <div className="modal-actions">
                <IconButton type="submit" icon={saveIcon} alt="Добавить" className="btn--primary" />
                <IconButton
                  type="button"
                  onClick={() => setAddStopOpen(false)}
                  icon={cancelIcon}
                  alt="Отмена"
                />
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default PricelistPage;
