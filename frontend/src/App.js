import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, NavLink } from "react-router-dom";
import axios from "axios";
import StopsPage from "./pages/StopsPage";
import RoutesPage from "./pages/RoutesPage";
import PricelistsPage from "./pages/PricelistsPage";
import SearchPage from "./pages/SearchPage";
import ToursPage from "./pages/ToursPage";
import ReportPage from "./pages/ReportPage";
import LoginPage from "./pages/LoginPage";
import PurchasesPage from "./pages/PurchasesPage";

import './App.css'; 

function App() {
  const [token, setToken] = useState(localStorage.getItem("token"));

  const handleLogin = () => {
    setToken(localStorage.getItem("token"));
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
  };

  useEffect(() => {
    const verify = async () => {
      if (token) {
        try {
          await axios.get("/auth/verify");
        } catch (err) {
          handleLogout();
        }
      }
    };
    verify();
  }, [token]);

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <Router>
      <nav>
        <ul>
          <li>
            <NavLink to="/stops" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Stops
            </NavLink>
          </li>
          <li>
            <NavLink to="/routes" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Routes
            </NavLink>
          </li>
          <li>
            <NavLink to="/pricelists" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Pricelists
            </NavLink>
          </li>
          <li>
            <NavLink to="/tours" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Tours
            </NavLink>
          </li>
          <li>
            <NavLink to="/report" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Report
            </NavLink>
          </li>
          <li>
            <NavLink to="/search" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Search
            </NavLink>
          </li>
          <li>
            <NavLink to="/purchases" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Purchases
            </NavLink>
          </li>
          <li>
            <button onClick={handleLogout}>Logout</button>
          </li>
        </ul>
      </nav>
      <Routes>
        <Route path="/stops" element={<StopsPage />} />
        <Route path="/routes" element={<RoutesPage />} />
        <Route path="/pricelists" element={<PricelistsPage />} />
        <Route path="/tours" element={<ToursPage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/purchases" element={<PurchasesPage />} />

      </Routes>
    </Router>
  );
}

export default App;

