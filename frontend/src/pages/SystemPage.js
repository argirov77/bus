import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "../config";
import { useToast } from "../components/Toast";

function extractFilename(contentDisposition, fallback) {
  if (!contentDisposition) return fallback;
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(contentDisposition);
  if (!match) return fallback;
  const encoded = match[1] || match[2];
  try {
    return decodeURIComponent(encoded);
  } catch (err) {
    return encoded;
  }
}

export default function SystemPage() {
  const addToast = useToast();
  const [downloading, setDownloading] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [confirmFile, setConfirmFile] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    document.title = "Система — Бэкап БД";
  }, []);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const response = await axios.get(`${API}/admin/backup/download`, {
        responseType: "blob",
      });
      const filename = extractFilename(
        response.headers && (response.headers["content-disposition"] || response.headers["Content-Disposition"]),
        `bustickets-backup-${Date.now()}.sql.gz`
      );
      const blob = new Blob([response.data], { type: "application/gzip" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      addToast(`Бэкап скачан: ${filename}`, "success");
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "Не удалось скачать бэкап";
      addToast(`Ошибка: ${detail}`, "error");
    } finally {
      setDownloading(false);
    }
  };

  const handleFilePick = (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) {
      setConfirmFile(file);
    }
    // Reset input so picking the same file again still triggers onChange.
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const cancelRestore = () => setConfirmFile(null);

  const doRestore = async () => {
    if (!confirmFile) return;
    const file = confirmFile;
    setConfirmFile(null);
    setRestoring(true);
    setLastResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await axios.post(`${API}/admin/backup/restore`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 10 * 60 * 1000,
      });
      setLastResult(response.data);
      addToast("База восстановлена. Обновите страницу.", "success");
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "Не удалось восстановить базу";
      setLastResult({ status: "error", detail });
      addToast(`Ошибка восстановления: ${detail}`, "error");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div style={{ padding: 20, maxWidth: 800 }}>
      <h1>Система</h1>

      <section style={{ marginTop: 24, padding: 16, border: "1px solid #ddd", borderRadius: 8 }}>
        <h2 style={{ marginTop: 0 }}>Резервная копия БД</h2>
        <p>
          Скачайте полный дамп базы данных (gzipped SQL). Файл сохраните в надёжное место —
          его можно использовать для восстановления при переезде на новый сервер или после сбоя.
        </p>
        <button
          className="btn btn--primary"
          onClick={handleDownload}
          disabled={downloading || restoring}
        >
          {downloading ? "Готовим бэкап…" : "Скачать бэкап БД"}
        </button>
      </section>

      <section style={{ marginTop: 24, padding: 16, border: "1px solid #f0caca", borderRadius: 8, background: "#fff8f8" }}>
        <h2 style={{ marginTop: 0, color: "#a00" }}>Восстановление из файла</h2>
        <p style={{ color: "#a00" }}>
          <strong>Внимание!</strong> Текущие данные будут полностью заменены содержимым файла.
          Действие необратимо. Используйте только файл бэкапа из этой системы (<code>.sql.gz</code>).
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".sql,.gz,.sql.gz,application/gzip,application/sql"
          onChange={handleFilePick}
          disabled={restoring}
          style={{ display: "block", marginTop: 8 }}
        />
        {restoring && <p style={{ marginTop: 12 }}>Восстановление… это может занять минуту.</p>}
        {lastResult && lastResult.status === "ok" && (
          <p style={{ marginTop: 12, color: "#070" }}>
            Готово. Залито {Math.round((lastResult.size_bytes || 0) / 1024)} КБ SQL.
          </p>
        )}
      </section>

      {confirmFile && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
          }}
        >
          <div style={{ background: "#fff", padding: 24, borderRadius: 8, maxWidth: 480 }}>
            <h3 style={{ marginTop: 0 }}>Подтвердите восстановление</h3>
            <p>
              Будет восстановлено из файла:<br />
              <strong>{confirmFile.name}</strong> ({Math.round(confirmFile.size / 1024)} КБ)
            </p>
            <p style={{ color: "#a00" }}>
              Все текущие записи в базе будут заменены. Это необратимо.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="btn btn--ghost" onClick={cancelRestore}>Отмена</button>
              <button className="btn btn--primary" onClick={doRestore} style={{ background: "#a00" }}>
                Восстановить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
