const DEFAULT_FALLBACK_PORT = process.env.REACT_APP_API_FALLBACK_PORT || "8000";

const guessApiUrl = () => {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const { protocol, hostname, port } = window.location;

    if (!hostname) {
      return null;
    }

    const normalizedHostname = hostname.toLowerCase();
    const isLocalHostName =
      normalizedHostname === "localhost" ||
      normalizedHostname === "127.0.0.1" ||
      normalizedHostname === "0.0.0.0" ||
      normalizedHostname.endsWith(".local");

    if (!isLocalHostName) {
      return null;
    }

    // Front-end dev server usually runs on 3000 while API on 8000.
    if (port === "3000") {
      return `${protocol}//${hostname}:${DEFAULT_FALLBACK_PORT}`;
    }

    if (!port || port === "80" || port === "443") {
      return `${protocol}//${hostname}:${DEFAULT_FALLBACK_PORT}`;
    }

    return `${protocol}//${hostname}:${port}`;
  } catch (error) {
    // fall back to localhost when window data cannot be parsed
    return null;
  }
};

const DEFAULT_REMOTE_API_URL = "/api";

const guessedApiUrl = guessApiUrl();
const fallbackApiUrl = guessedApiUrl || DEFAULT_REMOTE_API_URL;

const getConfiguredApiUrl = () => {
  const configuredApiUrl = (process.env.REACT_APP_API_URL || "").trim();
  if (!configuredApiUrl) {
    return fallbackApiUrl;
  }

  // Keep local/dev absolute URLs, force same-origin in production.
  if (configuredApiUrl.startsWith("/")) {
    return configuredApiUrl;
  }

  try {
    const parsed = new URL(configuredApiUrl);
    const isLocalHost =
      parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    return isLocalHost ? configuredApiUrl : DEFAULT_REMOTE_API_URL;
  } catch (error) {
    return DEFAULT_REMOTE_API_URL;
  }
};

export const API_URL = getConfiguredApiUrl();
export const API = API_URL; // backward compatibility
