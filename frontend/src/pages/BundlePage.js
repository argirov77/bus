import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../config";

export default function BundlePage() {
  const [routes, setRoutes] = useState([]);
  const [pricelists, setPricelists] = useState([]);
  const [bundle, setBundle] = useState({
    route_forward_id: "",
    route_backward_id: "",
    pricelist_id: "",
  });

  useEffect(() => {
    axios.get(`${API}/routes`).then(res => setRoutes(res.data));
    axios.get(`${API}/pricelists`).then(res => setPricelists(res.data));
    axios.get(`${API}/admin/route_pricelist_bundle`)
      .then(res => {
        if (res.data) {
          setBundle({
            route_forward_id: String(res.data.route_forward_id),
            route_backward_id: String(res.data.route_backward_id),
            pricelist_id: String(res.data.pricelist_id),
          });
        }
      })
      .catch(() => {});
  }, []);

  const handleSave = e => {
    e.preventDefault();
    axios.post(`${API}/admin/route_pricelist_bundle`, {
      route_forward_id: Number(bundle.route_forward_id),
      route_backward_id: Number(bundle.route_backward_id),
      pricelist_id: Number(bundle.pricelist_id)
    }).then(() => {
      alert("Bundle saved");
    }).catch(err => {
      console.error(err);
      alert("Error saving bundle");
    });
  };

  return (
    <div className="container">
      <h2>Настройка Bundle</h2>
      <form onSubmit={handleSave} style={{display:"flex",flexDirection:"column",gap:"8px",maxWidth:400}}>
        <label>
          Маршрут туда:
          <select value={bundle.route_forward_id} onChange={e=>setBundle({...bundle, route_forward_id:e.target.value})} required>
            <option value="">Выберите маршрут</option>
            {routes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <label>
          Маршрут обратно:
          <select value={bundle.route_backward_id} onChange={e=>setBundle({...bundle, route_backward_id:e.target.value})} required>
            <option value="">Выберите маршрут</option>
            {routes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <label>
          Прайслист:
          <select value={bundle.pricelist_id} onChange={e=>setBundle({...bundle, pricelist_id:e.target.value})} required>
            <option value="">Выберите прайслист</option>
            {pricelists.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <button type="submit">Сохранить bundle</button>
      </form>
    </div>
  );
}
