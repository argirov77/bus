import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../config";

export default function PublicBundlePage({ lang = "ru" }) {
  const [routesData, setRoutesData] = useState(null);
  const [plData, setPlData] = useState(null);

  useEffect(() => {
    axios.get(`${API}/public/routes_bundle`, { params: { lang } })
      .then(res => setRoutesData(res.data));
    axios.get(`${API}/public/pricelist_bundle`, { params: { lang } })
      .then(res => setPlData(res.data));
  }, [lang]);

  if (!routesData || !plData) return <p>Loading...</p>;

  return (
    <div className="container">
      <h3>{plData.pricelist.name}</h3>
      <div style={{ display: "flex", gap: "40px" }}>
        {[routesData.forward, routesData.backward].map((r, idx) => (
          <div key={idx}>
            <h4>{r.name}</h4>
            <ul>
              {r.stops.map(s => (
                <li key={s.id}>{s.name}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <table className="styled-table" style={{ marginTop: 20 }}>
        <thead>
          <tr>
            <th>Откуда</th>
            <th>Куда</th>
            <th>Цена</th>
          </tr>
        </thead>
        <tbody>
          {plData.prices.map((p, i) => (
            <tr key={i}>
              <td>{p.departure_stop_name}</td>
              <td>{p.arrival_stop_name}</td>
              <td>{p.price}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
