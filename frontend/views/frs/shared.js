// Shared FRS UI helpers (badge colour maps, formatters) — ported from vizor_nvr's
// frsShared.js, re-themed to our kit Badge colours.

export const ENROLL_COLOR = { enrolled: "green", pending: "amber", failed: "red", unenrolled: "slate" };
export const EVENT_COLOR = { face_recognized: "green", face_unknown: "amber", spoof_detected: "red", face_detected: "blue" };
export const CATEGORY_COLOR = { vip: "indigo", monitored: "amber", restricted: "amber", banned: "red", standard: "slate" };
export const SESSION_COLOR = { open: "amber", completed: "green", closed: "green", overdue: "red" };

export const CATEGORIES = [
  { value: "standard", label: "Standard" },
  { value: "vip", label: "VIP" },
  { value: "monitored", label: "Monitored" },
  { value: "restricted", label: "Restricted" },
  { value: "banned", label: "Banned" },
];

export const GROUP_TYPES = [
  { value: "employee", label: "Employee" },
  { value: "vip", label: "VIP" },
  { value: "watchlist", label: "Watchlist" },
  { value: "banned", label: "Banned" },
  { value: "visitor", label: "Visitor" },
];

export const GROUP_TYPE_COLOR = { employee: "blue", vip: "indigo", watchlist: "amber", banned: "red", visitor: "slate" };

export const SWATCHES = ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899", "#64748b"];

// --- cameras ---------------------------------------------------------------
export const CAM_STATUS_COLOR = { online: "green", offline: "slate", error: "red", connecting: "amber" };
export const CAM_DIRECTIONS = [
  { value: "both", label: "Both ways" },
  { value: "entry", label: "Entry" },
  { value: "exit", label: "Exit" },
];
export const CAM_HWACCEL = [
  { value: "none", label: "CPU (software)" },
  { value: "nvdec", label: "NVDEC (GPU)" },
];

export function confColor(c) {
  if (c == null) return "slate";
  if (c >= 0.85) return "green";
  if (c >= 0.6) return "amber";
  return "red";
}

export function fmt(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}

export function fmtTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? String(ts) : d.toLocaleTimeString();
}

export function fmtDuration(sec) {
  if (sec == null) return "—";
  sec = Math.round(sec);
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

export function pct(v) {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}
