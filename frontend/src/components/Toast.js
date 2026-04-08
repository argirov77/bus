import React, { useState, useCallback, useEffect, createContext, useContext } from "react";

const ToastContext = createContext(null);

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = "success") => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type }]);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <ToastItem key={t.id} toast={t} onDone={() => removeToast(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDone }) {
  useEffect(() => {
    const timer = setTimeout(onDone, 3500);
    return () => clearTimeout(timer);
  }, [onDone]);

  const bgColors = {
    success: "var(--success)",
    error: "var(--danger)",
    info: "var(--primary)",
    warning: "var(--warning)"
  };

  return (
    <div
      className="toast-item"
      style={{ backgroundColor: bgColors[toast.type] || bgColors.info }}
      role="status"
      aria-live="polite"
    >
      {toast.message}
      <button className="toast-close" onClick={onDone} aria-label="Закрыть">&times;</button>
    </div>
  );
}
