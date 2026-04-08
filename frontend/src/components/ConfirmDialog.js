import React, { useEffect, useRef } from "react";

export default function ConfirmDialog({ open, title, message, onConfirm, onCancel, confirmText = "Удалить", danger = true }) {
  const confirmRef = useRef(null);

  useEffect(() => {
    if (open && confirmRef.current) {
      confirmRef.current.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKey = (e) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title" onClick={onCancel}>
      <div className="modal-sheet" style={{ maxWidth: 420, padding: 24 }} onClick={e => e.stopPropagation()}>
        <h3 id="confirm-title" style={{ margin: 0 }}>{title || "Подтверждение"}</h3>
        {message && <p style={{ margin: "8px 0 16px", color: "var(--muted)" }}>{message}</p>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn--ghost" onClick={onCancel}>Отмена</button>
          <button
            ref={confirmRef}
            className={`btn ${danger ? "btn--danger" : "btn--primary"}`}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
