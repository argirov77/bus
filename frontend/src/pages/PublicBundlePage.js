import React, { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../config";

export default function PublicBundlePage() {
  const [lang, setLang] = useState("bg");
  const [routes, setRoutes] = useState([]);
  const [pricelist, setPricelist] = useState(null);

  useEffect(() => {
    axios.post(`${API}/public/routes_bundle`, { lang })
      .then(res => setRoutes(res.data))
      .catch(() => setRoutes([]));
    axios.post(`${API}/public/pricelist_bundle`, { lang })
      .then(res => setPricelist(res.data))
      .catch(() => setPricelist(null));
  }, [lang]);

  return (
    <div className="container">
      <h2>Маршруты и цены</h2>
      <select value={lang} onChange={e => setLang(e.target.value)}>
        <option value="bg">BG</option>
        <option value="en">EN</option>
        <option value="ua">UA</option>
        <option value="ru">RU</option>
      </select>

      {routes.map(rt => (
        <div key={rt.id} style={{marginTop:"1rem"}}>
          <h3>{rt.name}</h3>
          <ul>
            {rt.stops.map(st => (
              <li key={st.id}>
                {st.name} ({st.arrival_time} - {st.departure_time})
              </li>
            ))}
          </ul>
        </div>
      ))}

      {pricelist && (
        <div style={{marginTop:"2rem"}}>
          <h3>{pricelist.name}</h3>
          <ul>
            {pricelist.prices.map(p => (
              <li key={p.id}>
                {p.departure_name} – {p.arrival_name}: {p.price}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
