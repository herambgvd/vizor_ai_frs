"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import { Badge, Input, Spinner } from "@/web/kit";
import { api, fileUrl } from "@/web/api";

import { EVENT_COLOR, confColor, fmtTime, pct } from "./shared";

const DOT = { enrolled: "bg-green-500", pending: "bg-amber-500", failed: "bg-red-500", unenrolled: "bg-slate-500" };

function dayKey(iso) { if (!iso) return ""; const d = new Date(iso); return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10); }
function fmtDay(iso) { if (!iso) return "—"; const d = new Date(iso); return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }); }
function relative(iso) {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function Avatar({ thumb, className = "h-10 w-10" }) {
  return (
    <div className={`${className} rounded-lg bg-hover overflow-hidden flex items-center justify-center shrink-0`}>
      {thumb ? <img src={fileUrl(thumb)} alt="" className="h-full w-full object-cover" /> : <Icon icon="heroicons-outline:user-circle" className="text-muted text-xl" />}
    </div>
  );
}

function PersonList({ selectedId, onSelect }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(search.trim()), 300); return () => clearTimeout(t); }, [search]);

  const persons = useQuery({
    queryKey: ["frs-persons", "tour", debounced],
    queryFn: () => api.get("/frs/persons", { params: { limit: 100, search: debounced || undefined } }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
  const items = persons.data?.items || [];
  const total = persons.data?.total ?? items.length;

  return (
    <div className="lg:col-span-3 rounded-xl border border-card-border bg-card flex flex-col min-h-0 overflow-hidden">
      <div className="p-2.5 border-b border-card-border space-y-2">
        <div className="flex items-center gap-2 px-1 text-xs uppercase tracking-wider text-muted"><Icon icon="heroicons-outline:user-circle" /> POI · {total}</div>
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name…" />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1">
        {persons.isLoading ? (
          <div className="flex justify-center py-10"><Spinner /></div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-muted"><Icon icon="heroicons-outline:user-circle" className="text-2xl" /><span className="text-xs uppercase tracking-wider">No persons found</span></div>
        ) : (
          items.map((p) => (
            <button key={p.id} type="button" onClick={() => onSelect(p)}
              className={`w-full text-left flex items-center gap-2.5 p-2 rounded-lg border transition ${selectedId === p.id ? "border-blue-500 bg-hover" : "border-transparent hover:bg-hover"}`}>
              <Avatar thumb={p.thumbnail_key} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-foreground truncate">{p.full_name}</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={`h-2 w-2 rounded-full shrink-0 ${DOT[p.enrollment_status] || "bg-slate-500"}`} />
                  <span className="text-[10px] uppercase tracking-wider text-muted truncate">{p.enrollment_status || "unenrolled"}{p.external_id ? ` · ${p.external_id}` : ""}</span>
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div className="rounded-lg border border-card-border bg-hover/40 p-2.5">
      <div className="flex items-center justify-between"><span className="text-[10px] uppercase tracking-wider text-muted">{label}</span><Icon icon={icon} className="text-muted" /></div>
      <div className="mt-1 text-lg font-semibold text-foreground truncate tabular-nums">{value}</div>
    </div>
  );
}

function EventCard({ e }) {
  return (
    <div className="rounded-lg border border-card-border bg-card overflow-hidden self-start">
      <div className="relative aspect-square bg-black/40">
        {e.snapshot_url ? <img src={fileUrl(e.snapshot_url)} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" /> : <div className="absolute inset-0 flex items-center justify-center"><Icon icon="heroicons-outline:photo" className="text-muted" /></div>}
        <span className="absolute top-1 left-1"><Badge color={EVENT_COLOR[e.event_type] || "slate"}>{e.confidence != null ? pct(e.confidence) : (e.event_type || "").replace(/_/g, " ")}</Badge></span>
      </div>
      <div className="px-2 py-1.5">
        <div className="flex items-center gap-1 min-w-0 text-xs text-foreground"><Icon icon="heroicons-outline:video-camera" className="text-muted shrink-0" /><span className="truncate font-medium">{e.camera_name || "—"}</span></div>
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted mt-0.5"><span>{fmtTime(e.triggered_at)}</span><span className={`text-${confColor(e.confidence)}-500`}>{pct(e.confidence)}</span></div>
      </div>
    </div>
  );
}

function TimelinePane({ person }) {
  const q = useQuery({
    queryKey: ["frs-tour-timeline", person?.id],
    queryFn: () => api.get(`/frs/tour/timeline/${person.id}`).then((r) => r.data),
    enabled: !!person,
  });
  const entries = q.data?.timeline || [];

  const stats = useMemo(() => {
    const cams = new Set(); let last = null;
    for (const e of entries) {
      if (e.camera_id) cams.add(e.camera_id);
      if (e.triggered_at) { const t = new Date(e.triggered_at).getTime(); if (!Number.isNaN(t) && (last == null || t > last)) last = t; }
    }
    return { total: entries.length, cameras: cams.size, lastSeen: last != null ? new Date(last).toISOString() : null };
  }, [entries]);

  const grouped = useMemo(() => {
    const m = new Map();
    for (const e of entries) { const k = dayKey(e.triggered_at); if (!m.has(k)) m.set(k, []); m.get(k).push(e); }
    for (const arr of m.values()) arr.sort((a, b) => new Date(b.triggered_at || 0) - new Date(a.triggered_at || 0));
    return Array.from(m.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [entries]);

  if (!person) {
    return <div className="h-full flex flex-col items-center justify-center gap-2 p-6 text-muted"><Icon icon="heroicons-outline:map" className="text-3xl" /><span className="text-xs uppercase tracking-wider text-center">Pick a person to trace where &amp; when they were seen</span></div>;
  }
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="px-4 py-3 border-b border-card-border">
        <div className="flex items-center gap-2.5 min-w-0">
          <Avatar thumb={person.thumbnail_key} className="h-9 w-9" />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-foreground truncate">{person.full_name}</div>
            {person.external_id && <div className="text-[10px] uppercase tracking-wider text-muted truncate">{person.external_id}</div>}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 mt-3">
          <Stat icon="heroicons-outline:eye" label="Sightings" value={stats.total} />
          <Stat icon="heroicons-outline:video-camera" label="Cameras" value={stats.cameras} />
          <Stat icon="heroicons-outline:clock" label="Last seen" value={stats.lastSeen ? relative(stats.lastSeen) : "—"} />
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-5">
        {q.isLoading ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : entries.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 rounded-lg border border-dashed border-card-border text-muted"><Icon icon="heroicons-outline:map" className="text-2xl" /><span className="text-xs uppercase tracking-wider">No sightings recorded</span></div>
        ) : (
          grouped.map(([day, dayEntries]) => (
            <div key={day || "unknown"}>
              <div className="sticky top-0 z-10 flex items-center justify-between px-1 py-1.5 mb-2 bg-card border-b border-card-border">
                <span className="text-xs uppercase tracking-wider font-semibold text-foreground">{fmtDay(dayEntries[0]?.triggered_at)}</span>
                <span className="text-[10px] uppercase tracking-wider text-muted">{dayEntries.length} sighting{dayEntries.length !== 1 ? "s" : ""}</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {dayEntries.map((e, i) => <EventCard key={e.event_id || i} e={e} />)}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function TourTab() {
  const [person, setPerson] = useState(null);
  return (
    <div className="grid grid-cols-1 lg:grid-cols-10 gap-4 h-[calc(100vh-200px)] min-h-[520px]">
      <PersonList selectedId={person?.id} onSelect={setPerson} />
      <div className="lg:col-span-7 rounded-xl border border-card-border bg-card flex flex-col min-h-0 overflow-hidden">
        <TimelinePane person={person} />
      </div>
    </div>
  );
}
