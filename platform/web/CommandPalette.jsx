"use client";

import { Icon } from "@iconify/react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/web/api";
import { menuItems } from "@/menu";
import { useAuth } from "@/web/auth";

// Flatten the nav into a list of {title, link, icon, perm} entries the palette
// can offer as "Pages" (children are hoisted; parents with children are dropped).
function navPages() {
  const out = [];
  for (const item of menuItems) {
    if (item.children) {
      for (const c of item.children) out.push(c);
    } else if (item.link) {
      out.push(item);
    }
  }
  out.push({ title: "My account", link: "/account", icon: "heroicons-outline:user-circle" });
  return out;
}

export default function CommandPalette() {
  const router = useRouter();
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  // Global ⌘K / Ctrl-K toggle.
  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    }
    function onOpen() {
      setOpen(true);
    }
    document.addEventListener("keydown", onKey);
    window.addEventListener("palette:open", onOpen);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("palette:open", onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setResults([]);
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  const pages = useMemo(
    () => navPages().filter((p) => !p.perm || can(p.perm)),
    [can]
  );

  // Debounced entity search (users, roles).
  useEffect(() => {
    if (!open) return;
    const term = q.trim();
    if (!term) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get("/search", { params: { q: term } });
        setResults(data.results || []);
      } catch {
        setResults([]);
      }
    }, 180);
    return () => clearTimeout(t);
  }, [q, open]);

  const pageMatches = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return pages;
    return pages.filter((p) => p.title.toLowerCase().includes(term));
  }, [q, pages]);

  // A single flat list for keyboard navigation: pages first, then entities.
  const flat = useMemo(
    () => [
      ...pageMatches.map((p) => ({ kind: "page", label: p.title, icon: p.icon, href: p.link })),
      ...results.map((r) => ({
        kind: "entity",
        label: r.label,
        sublabel: r.sublabel,
        icon: r.icon,
        href: r.href,
      })),
    ],
    [pageMatches, results]
  );

  const go = useCallback(
    (item) => {
      if (!item) return;
      setOpen(false);
      router.push(item.href);
    },
    [router]
  );

  function onInputKey(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(flat[active]);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[12vh] px-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-xl rounded-xl bg-card border border-card-border shadow-2xl animate-modal-in overflow-hidden">
        <div className="flex items-center gap-2 px-4 border-b border-card-border">
          <Icon icon="heroicons-outline:magnifying-glass" className="text-muted text-lg shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={onInputKey}
            placeholder="Search pages, users, roles…"
            className="w-full bg-transparent py-3.5 text-sm text-foreground placeholder:text-muted outline-none"
          />
          <kbd className="text-[10px] text-muted border border-card-border rounded px-1.5 py-0.5">ESC</kbd>
        </div>

        <div className="max-h-[50vh] overflow-y-auto py-2">
          {flat.length === 0 ? (
            <p className="text-sm text-muted text-center py-8">No results.</p>
          ) : (
            flat.map((item, i) => (
              <button
                key={`${item.kind}-${i}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(item)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition ${
                  i === active ? "bg-hover" : ""
                }`}
              >
                <Icon icon={item.icon || "heroicons-outline:arrow-right"} className="text-base text-muted shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] text-foreground truncate">{item.label}</div>
                  {item.sublabel && <div className="text-xs text-muted truncate">{item.sublabel}</div>}
                </div>
                <span className="text-[10px] text-muted uppercase">{item.kind}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
