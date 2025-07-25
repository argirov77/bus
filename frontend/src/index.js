import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import axios from "axios";
import { API_URL } from "./config";

axios.defaults.baseURL = API_URL;
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers = config.headers || {};
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
