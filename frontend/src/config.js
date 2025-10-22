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

const fallbackApiUrl = guessApiUrl() || `http://localhost:${DEFAULT_FALLBACK_PORT}`;

export const API_URL = process.env.REACT_APP_API_URL || fallbackApiUrl;
export const API = API_URL; // backward compatibility
