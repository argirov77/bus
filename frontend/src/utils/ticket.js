import axios from "axios";
import { API } from "../config";

function extractFilename(contentDisposition, fallback) {
  if (!contentDisposition) {
    return fallback;
  }
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(contentDisposition);
  if (!match) {
    return fallback;
  }
  const encoded = match[1] || match[2];
  try {
    return decodeURIComponent(encoded);
  } catch (err) {
    return encoded;
  }
}

function resolveToken({ token, deepLink }) {
  if (token) {
    return token;
  }
  if (!deepLink) {
    return undefined;
  }
  try {
    const url = new URL(deepLink);
    return url.searchParams.get("token") || undefined;
  } catch (err) {
    return undefined;
  }
}

export async function downloadTicketPdf(ticketId, options = {}) {
  if (!ticketId) {
    throw new Error("Ticket id is required to download PDF");
  }
  const token = resolveToken(options);
  const params = token ? { token } : undefined;

  const response = await axios.get(`${API}/tickets/${ticketId}/pdf`, {
    responseType: "blob",
    params,
  });

  const filename = extractFilename(
    response.headers && (response.headers["content-disposition"] || response.headers["Content-Disposition"]),
    `ticket-${ticketId}.pdf`
  );

  const blob = new Blob([response.data], { type: "application/pdf" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
