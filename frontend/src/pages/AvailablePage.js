import React, {useEffect, useState} from "react";
import axios from "axios";

import { API } from "../config";

function AvailablePage() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    axios.get(`${API}/available`)
      .then(response => setItems(response.data))
      .catch(error => console.error("Ошибка при получении данных:", error));
  }, []);

  return (
    <div>
      <h2>AvailablePage</h2>
      <ul>
        {items.map((item, index) => (
          <li key={index}>{JSON.stringify(item)}</li>
        ))}
      </ul>
    </div>
  );
}

export default AvailablePage;
