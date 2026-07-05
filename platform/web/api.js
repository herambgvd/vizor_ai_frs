// Axios instance wired to the edge backend (/api/v1). Attaches the JWT on every
// request; on 401 it clears the session and bounces to /login; on LICENSE_EXPIRED
// it routes to the "License Expired" screen so an admin can renew.
import axios from "axios";

// Derive the API host from wherever the UI is loaded — so accessing the app from
// another machine on the LAN (http://<host-ip>:3000) hits that same host's :8000.
const apiHost = typeof window !== "undefined" ? window.location.hostname : "localhost";
const BASE = process.env.NEXT_PUBLIC_API_URL || `http://${apiHost}:8000`;

export const ACCESS_KEY = "vizor.access";
export const REFRESH_KEY = "vizor.refresh";

export const tokens = {
  get access() {
    return typeof window !== "undefined" ? localStorage.getItem(ACCESS_KEY) : null;
  },
  get refresh() {
    return typeof window !== "undefined" ? localStorage.getItem(REFRESH_KEY) : null;
  },
  set(access, refresh) {
    if (typeof window === "undefined") return;
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    if (typeof window === "undefined") return;
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({ baseURL: `${BASE}/api/v1` });

api.interceptors.request.use((config) => {
  const t = tokens.access;
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    const code = error?.response?.data?.error?.code;
    if (typeof window !== "undefined") {
      if (error?.response?.status === 401) {
        tokens.clear();
        if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
      } else if (code === "LICENSE_EXPIRED") {
        window.location.href = "/license-expired";
      }
    }
    return Promise.reject(error);
  }
);

// Unwrap the uniform error envelope { error: { code, message } } into a string.
export function apiError(error, fallback = "Something went wrong") {
  return error?.response?.data?.error?.message || error?.message || fallback;
}

// Resolve a backend file reference to an absolute URL the browser can load.
// The backend returns object URLs relative to its own origin ("/files/<key>"),
// but the UI runs on a different port in dev — so prefix the backend base.
// Pass either a "/files/..." url or a raw storage key.
export function fileUrl(ref) {
  if (!ref) return null;
  if (/^https?:\/\//.test(ref)) return ref;      // already absolute (e.g. S3 presigned)
  const path = ref.startsWith("/files/") ? ref : `/files/${ref.replace(/^\//, "")}`;
  return `${BASE}${path}`;
}
