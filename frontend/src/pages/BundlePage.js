import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../config";

export default function BundlePage() {
  const [routes, setRoutes] = useState([]);
  const [pricelists, setPricelists] = useState([]);

  const [forward, setForward] = useState("");
  const [backward, setBackward] = useState("");
  const [pricelist, setPricelist] = useState("");

  useEffect(() => {
    axios.get(`${API}/routes`).then(res => setRoutes(res.data));
    axios.get(`${API}/pricelists`).then(res => setPricelists(res.data));
    axios.get(`${API}/admin/route_pricelist_bundle`).then(res => {
      if (res.data) {
        setForward(res.data.route_forward_id);
        setBackward(res.data.route_backward_id);
        setPricelist(res.data.pricelist_id);
      }
    });
  }, []);

  const handleSave = () => {
    if (!forward || !backward || !pricelist) return;
    axios.post(`${API}/admin/route_pricelist_bundle`, {
      route_forward_id: Number(forward),
      route_backward_id: Number(backward),
      pricelist_id: Number(pricelist)
    });
  };

  return (
    <div className="container">
      <h2>Bundle</h2>
      <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        <select value={forward} onChange={e => setForward(e.target.value)}>
          <option value="">Forward route</option>
          {routes.map(r => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
        <select value={backward} onChange={e => setBackward(e.target.value)}>
          <option value="">Backward route</option>
          {routes.map(r => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
        <select value={pricelist} onChange={e => setPricelist(e.target.value)}>
          <option value="">Pricelist</option>
          {pricelists.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <button onClick={handleSave}>Сохранить bundle</button>
      </div>
    </div>
  );
}
