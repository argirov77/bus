import React, { useState } from "react";
import { BrowserRouter as Router, Routes, Route, NavLink } from "react-router-dom";
import StopsPage from "./pages/StopsPage";
import RoutesPage from "./pages/RoutesPage";
import PricelistsPage from "./pages/PricelistsPage";
import SearchPage from "./pages/SearchPage";
import ToursPage from "./pages/ToursPage";
import PassengersPage from "./pages/PassengersPage";
import ReportPage from "./pages/ReportPage";
import AvailablePage from "./pages/AvailablePage";
import LoginPage from "./pages/LoginPage";

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
            <NavLink to="/passengers" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Passengers
            </NavLink>
          </li>
          <li>
            <NavLink to="/report" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Report
            </NavLink>
          </li>
          <li>
            <NavLink to="/available" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Available
            </NavLink>
          </li>
          <li>
            <NavLink to="/search" className={({ isActive }) => (isActive ? "active" : undefined)}>
              Search
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
        <Route path="/passengers" element={<PassengersPage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/available" element={<AvailablePage />} />
        <Route path="/search" element={<SearchPage />} />

      </Routes>
    </Router>
  );
}

export default App;

