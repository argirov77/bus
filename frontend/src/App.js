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
import { ToastProvider } from "./components/Toast";
import { useToast } from "./components/Toast";

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
    <ToastProvider>
    <AdminCheckBoxHealth />
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
            <button className="btn btn--ghost btn--sm" onClick={handleLogout}>Logout</button>
          </li>
        </ul>
      </nav>
      <div className="fade-in">
        <Routes>
          <Route path="/stops" element={<StopsPage />} />
          <Route path="/routes" element={<RoutesPage />} />
          <Route path="/pricelists" element={<PricelistsPage />} />
          <Route path="/tours" element={<ToursPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/purchases" element={<PurchasesPage />} />
        </Routes>
      </div>
    </Router>
    </ToastProvider>
  );
}

function AdminCheckBoxHealth() {
  const addToast = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [checkedAt, setCheckedAt] = useState(null);

  const runHealth = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/admin/integrations/checkbox/health');
      setResult(response.data);
      setCheckedAt(new Date().toISOString());
      addToast(`CheckBox: ${response.data.status}`, response.data.status === 'ok' ? 'success' : 'warning');
    } catch (err) {
      const payload = err?.response?.data || { status: 'error', message: 'Request failed', details: [] };
      setResult(payload);
      setCheckedAt(new Date().toISOString());
      addToast(`CheckBox: ${payload.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const copyDetails = async () => {
    if (!result) return;
    const text = JSON.stringify({ status: result.status, http_status: result.http_status, message: result.message, details: result.details }, null, 2);
    await navigator.clipboard.writeText(text);
    addToast('Детали скопированы', 'info');
  };

  const color = result?.status === 'ok' ? 'green' : (result?.status === 'warning' || result?.status === 'disabled') ? '#d4a000' : 'red';

  return <div style={{ padding: '12px 16px', borderBottom: '1px solid #eee' }}>
    <button className="btn btn--sm" onClick={runHealth} disabled={loading}>{loading ? 'Проверка...' : 'Проверить CheckBox'}</button>
    {result && <div style={{ marginTop: 8 }}>
      <strong style={{ color }}>Статус: {result.status}</strong> — {result.message}
      {checkedAt && <div>Проверено: {checkedAt}</div>}
      {(result.http_status === 401 || result.http_status === 403) && <div>Подсказка: проверьте логин/пароль/ключи CheckBox.</div>}
      {String(result.message || '').toLowerCase().includes('network') && <div>Подсказка: проверьте интернет-доступ и CHECKBOX_API_URL.</div>}
      <ul>{(result.details || []).map((d, i) => <li key={i}>{d}</li>)}</ul>
      <button className="btn btn--ghost btn--sm" onClick={copyDetails}>Скопировать детали</button>
    </div>}
  </div>;
}

export default App;
