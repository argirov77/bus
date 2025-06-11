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
      <ul>
        {items.map((item, index) => (
          <li key={index}>{JSON.stringify(item)}</li>
        ))}
      </ul>
    </div>
  );
}

export default PricesPage;
