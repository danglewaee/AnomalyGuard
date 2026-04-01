function defaultApiBase() {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }

  const protocol = window.location.protocol === "https:" ? "https" : "http";
  const hostname = window.location.hostname || "localhost";
  return `${protocol}://${hostname}:8000`;
}

function toWebSocketBase(apiBase) {
  if (apiBase.startsWith("https://")) {
    return apiBase.replace("https://", "wss://");
  }
  if (apiBase.startsWith("http://")) {
    return apiBase.replace("http://", "ws://");
  }
  return apiBase;
}

export const API_BASE = (import.meta.env.VITE_API_BASE || defaultApiBase()).replace(/\/$/, "");
export const WS_URL = (import.meta.env.VITE_WS_URL || `${toWebSocketBase(API_BASE)}/ws/stream`).replace(/\/$/, "");
