"use client";

// Shared UI kit — theme-aware (Vercel style). Uses semantic tokens (background,
// foreground, card, card-border, muted, hover) that flip between light/dark.
import { Icon } from "@iconify/react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function Card({ className = "", children }) {
  return (
    <div className={`rounded-lg bg-card border border-card-border ${className}`}>{children}</div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">{title}</h1>
        {subtitle && <p className="text-muted mt-1 text-[13px]">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

const VARIANTS = {
  // Primary inverts with the theme (black-on-white in light, white-on-black in dark).
  primary: "bg-foreground text-background hover:opacity-90",
  success: "bg-green-600 hover:bg-green-500 text-white", // create actions
  danger: "bg-red-600 hover:bg-red-500 text-white", // delete actions
  secondary: "bg-transparent border border-card-border text-foreground hover:bg-hover",
  ghost: "bg-transparent text-muted hover:text-foreground hover:bg-hover",
};

export function Button({ variant = "primary", icon, className = "", children, ...props }) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition disabled:opacity-50 disabled:pointer-events-none ${VARIANTS[variant]} ${className}`}
    >
      {icon && <Icon icon={icon} className="text-base" />}
      {children}
    </button>
  );
}

const FIELD =
  "w-full rounded-md border border-field bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted";

export function Input({ label, hint, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-sm font-medium text-foreground mb-1.5">{label}</span>}
      <input {...props} className={`${FIELD} ${className}`} />
      {hint && <span className="block text-xs text-muted mt-1">{hint}</span>}
    </label>
  );
}

// Custom themed dropdown (replaces the native <select> for a consistent dark/light
// look). The options panel renders in a portal with fixed positioning so it never
// gets clipped by a scroll container (modals, tables). Drop-in compatible: emits
// onChange({ target: { value } }) like a native select.
export function Select({ label, options = [], value, onChange, disabled, placeholder, className = "" }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null); // { left, top?, bottom?, width }
  const btnRef = useRef(null);
  const panelRef = useRef(null);

  const selected = options.find((o) => String(o.value) === String(value ?? ""));
  const isPlaceholder = !selected || selected.value === "";
  const displayLabel = selected ? selected.label : placeholder || "Select…";

  useEffect(() => {
    if (!open) return;
    function onDoc(e) {
      if (btnRef.current?.contains(e.target) || panelRef.current?.contains(e.target)) return;
      setOpen(false);
    }
    // Fixed-positioned panel can't follow scroll, so close on any scroll/resize.
    function onScroll() {
      setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  function toggle() {
    if (disabled) return;
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const dropUp = window.innerHeight - r.bottom < 260 && r.top > 260;
      setPos({
        left: r.left,
        width: r.width,
        top: dropUp ? undefined : r.bottom + 4,
        bottom: dropUp ? window.innerHeight - r.top + 4 : undefined,
      });
    }
    setOpen((o) => !o);
  }

  function pick(v) {
    onChange?.({ target: { value: v } });
    setOpen(false);
  }

  return (
    <div className="block">
      {label && <span className="block text-sm font-medium text-foreground mb-1.5">{label}</span>}
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        onClick={toggle}
        className={`${FIELD} flex items-center justify-between text-left ${
          isPlaceholder ? "!text-muted" : ""
        } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"} ${className}`}
      >
        <span className="truncate">{displayLabel}</span>
        <Icon
          icon="heroicons-outline:chevron-down"
          className={`text-base shrink-0 ml-2 text-muted transition ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && !disabled && pos && typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panelRef}
            style={{ position: "fixed", left: pos.left, width: pos.width, top: pos.top, bottom: pos.bottom, zIndex: 60 }}
            className="max-h-60 overflow-auto rounded-lg border border-card-border bg-card shadow-2xl py-1 animate-fade-in"
          >
            {options.map((o) => {
              const active = String(o.value) === String(value ?? "");
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => pick(o.value)}
                  className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-left transition ${
                    active ? "text-foreground bg-hover" : "text-muted hover:text-foreground hover:bg-hover"
                  }`}
                >
                  <span className="truncate">{o.label}</span>
                  {active && !isPlaceholder && <Icon icon="heroicons-outline:check" className="text-base shrink-0" />}
                </button>
              );
            })}
          </div>,
          document.body
        )}
    </div>
  );
}

export function Textarea({ label, className = "", ...props }) {
  return (
    <label className="block">
      {label && <span className="block text-sm font-medium text-foreground mb-1.5">{label}</span>}
      <textarea {...props} className={`${FIELD} ${className}`} />
    </label>
  );
}

const BADGE = {
  slate: "bg-hover text-muted border-card-border",
  neutral: "bg-hover text-muted border-card-border",
  green: "bg-green-500/10 text-green-500 border-green-500/20",
  red: "bg-red-500/10 text-red-500 border-red-500/20",
  indigo: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  blue: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  amber: "bg-amber-500/10 text-amber-500 border-amber-500/20",
};

export function Badge({ color = "neutral", children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${BADGE[color] || BADGE.neutral}`}
    >
      {children}
    </span>
  );
}

// Round profile picture: shows the image when a URL is given, otherwise the
// first initial on a neutral chip. `size` is the diameter in px.
export function Avatar({ src, name, size = 28, className = "" }) {
  const initials = (name || "?").trim().charAt(0).toUpperCase() || "?";
  const dim = { width: size, height: size };
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name || "Avatar"}
        style={dim}
        className={`rounded-full object-cover border border-card-border ${className}`}
      />
    );
  }
  return (
    <div
      style={dim}
      className={`rounded-full bg-hover border border-card-border text-foreground flex items-center justify-center font-semibold shrink-0 ${className}`}
    >
      <span style={{ fontSize: Math.round(size * 0.42) }}>{initials}</span>
    </div>
  );
}

export function Spinner({ className = "" }) {
  return (
    <div className={`h-6 w-6 rounded-full border-2 border-card-border border-t-foreground animate-spin ${className}`} />
  );
}

// Branded full-screen loader: the "N" mark inside a spinning ring. Used for the
// initial auth check and route-level loading fallbacks.
export function FullPageLoader({ label = "Loading" }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-background">
      <div className="relative h-14 w-14">
        <div className="absolute inset-0 rounded-full border-2 border-card-border border-t-foreground animate-spin" />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="h-7 w-7 rounded-md bg-white flex items-center justify-center text-black font-bold text-sm">
            N
          </div>
        </div>
      </div>
      {label && <p className="text-muted text-[13px] animate-pulse">{label}</p>}
    </div>
  );
}

export function EmptyState({ icon = "heroicons-outline:inbox", title, subtitle, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Icon icon={icon} className="text-4xl text-muted mb-3 opacity-60" />
      <p className="text-foreground font-medium">{title}</p>
      {subtitle && <p className="text-muted text-sm mt-1">{subtitle}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${
        checked ? "bg-foreground" : "bg-card-border"
      } disabled:opacity-40`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full transition ${
          checked ? "bg-background" : "bg-muted"
        }`}
        style={{ transform: checked ? "translateX(18px)" : "translateX(3px)" }}
      />
    </button>
  );
}

export function Modal({ open, onClose, title, children, footer, wide }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose?.();
    }
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div
        className={`relative w-full ${wide ? "max-w-2xl" : "max-w-md"} rounded-xl bg-card border border-card-border shadow-2xl animate-modal-in`}
      >
        <div className="flex items-center justify-between border-b border-card-border px-5 py-4">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-foreground transition">
            <Icon icon="heroicons-outline:x-mark" className="text-xl" />
          </button>
        </div>
        <div className="px-5 py-4 max-h-[70vh] overflow-y-auto">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-card-border px-5 py-4">{footer}</div>
        )}
      </div>
    </div>
  );
}

// Right-side sliding sheet for detail views (person detail, investigation history…).
export function Drawer({ open, onClose, title, subtitle, children, width = "max-w-md" }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose?.();
    }
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className={`relative h-full w-full ${width} bg-card border-l border-card-border shadow-2xl flex flex-col animate-modal-in`}>
        <div className="flex items-start justify-between border-b border-card-border px-5 py-4 shrink-0">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-foreground truncate">{title}</h3>
            {subtitle && <p className="text-xs text-muted mt-0.5 truncate">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="text-muted hover:text-foreground transition shrink-0 ml-3">
            <Icon icon="heroicons-outline:x-mark" className="text-xl" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

// A themed confirmation modal (replaces window.confirm). Drive it with a piece of
// state: setConfirm({ title, message, confirmLabel, danger, onConfirm }) to open,
// and render one <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} />.
export function ConfirmDialog({ state, onClose, pending }) {
  const cfg = state || {};
  return (
    <Modal
      open={!!state}
      onClose={onClose}
      title={cfg.title || "Are you sure?"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            {cfg.cancelLabel || "Cancel"}
          </Button>
          <Button
            variant={cfg.danger === false ? "primary" : "danger"}
            icon={cfg.icon}
            disabled={pending}
            onClick={() => cfg.onConfirm?.()}
          >
            {pending ? "Working…" : cfg.confirmLabel || "Delete"}
          </Button>
        </>
      }
    >
      {cfg.danger === false ? (
        <p className="text-sm text-foreground">{cfg.message}</p>
      ) : (
        <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2.5 text-sm text-red-500">
          <Icon icon="heroicons-outline:exclamation-triangle" className="text-base mt-0.5 shrink-0" />
          <span>{cfg.message || "This action cannot be undone."}</span>
        </div>
      )}
    </Modal>
  );
}

export function Table({ columns, rows, empty }) {
  if (!rows?.length) return empty || <EmptyState title="Nothing here yet" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted border-b border-card-border">
            {columns.map((c) => (
              <th key={c.key} className="font-medium px-4 py-3">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.id || i}
              className="border-b border-card-border hover:bg-hover transition"
            >
              {columns.map((c) => (
                <td key={c.key} className="px-4 py-3 text-foreground">
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
