import React, {useEffect, useState} from "react";
import axios from "axios";

import { API } from "../config";

function PricesPage() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    axios.get(`${API}/prices`)
      .then(response => setItems(response.data))
      .catch(error => console.error("Ошибка при получении данных:", error));
  }, []);

  return (
    <div>
      <h2>PricesPage</h2>
      <table className="styled-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>От остановки</th>
            <th>До остановки</th>
            <th>Цена</th>
            <th>Льготная цена</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.id}</td>
              <td>{item.departure_stop_name || item.departure_stop_id}</td>
              <td>{item.arrival_stop_name || item.arrival_stop_id}</td>
              <td>{item.price}</td>
              <td>{item.discount_price ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default PricesPage;
