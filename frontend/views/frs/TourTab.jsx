"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import { Badge, EmptyState, Input, Modal, Spinner } from "@/web/kit";
import { api, fileUrl } from "@/web/api";

import { EVENT_COLOR, confColor, fmtTime, pct } from "./shared";

const DOT = { enrolled: "bg-green-500", pending: "bg-amber-500", failed: "bg-red-500", unenrolled: "bg-slate-500" };
const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);

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

// Crops the face out of the full-frame snapshot using the (native-pixel) bbox.
// Falls back to the whole image for legacy crop-snapshots whose bbox won't fit.
function FaceCrop({ url, bbox, className = "h-full w-full", icon = "heroicons-outline:user" }) {
  const ref = useRef(null);
  const has = !!url && Array.isArray(bbox) && bbox.length === 4;
  useEffect(() => {
    if (!has) return;
    const canvas = ref.current;
    if (!canvas) return;
    const img = new window.Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const nw = img.naturalWidth, nh = img.naturalHeight;
      let [x1, y1, x2, y2] = bbox.map(Number);
      if (!(x2 > x1 && y2 > y1) || x2 > nw + 4 || y2 > nh + 4) {
        canvas.width = nw; canvas.height = nh;
        try { canvas.getContext("2d").drawImage(img, 0, 0); } catch { /* noop */ }
        return;
      }
      const bw = Math.max(1, x2 - x1), bh = Math.max(1, y2 - y1), pad = 0.3;
      x1 = Math.max(0, x1 - bw * pad); y1 = Math.max(0, y1 - bh * pad);
      x2 = Math.min(nw, x2 + bw * pad); y2 = Math.min(nh, y2 + bh * pad);
      const cw = Math.max(1, x2 - x1), ch = Math.max(1, y2 - y1);
      canvas.width = cw; canvas.height = ch;
      try { canvas.getContext("2d").drawImage(img, x1, y1, cw, ch, 0, 0, cw, ch); } catch { /* noop */ }
    };
    img.src = fileUrl(url);
  }, [url, has, JSON.stringify(bbox)]);
  if (!has) return <div className={`${className} flex items-center justify-center`}><Icon icon={icon} className="text-muted text-xl" /></div>;
  return <canvas ref={ref} className={`${className} object-cover`} />;
}

function DateInput({ label, value, onChange }) {
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      {label}
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-field bg-transparent px-2 py-1.5 text-xs text-foreground outline-none focus:border-muted" />
    </label>
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

function useSightings(entries) {
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

  return { stats, grouped };
}

function SightingsBody({ isLoading, grouped, emptyLabel }) {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-5">
      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : grouped.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-16 rounded-lg border border-dashed border-card-border text-muted"><Icon icon="heroicons-outline:map" className="text-2xl" /><span className="text-xs uppercase tracking-wider">{emptyLabel}</span></div>
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
  );
}

// ── POI tour: person list + their cross-camera timeline ──────────────────────
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
    <div className="lg:col-span-3 lg:h-full min-h-[320px] rounded-xl border border-card-border bg-card flex flex-col min-h-0 overflow-hidden">
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

function TimelinePane({ person }) {
  const q = useQuery({
    queryKey: ["frs-tour-timeline", person?.id],
    queryFn: () => api.get(`/frs/tour/timeline/${person.id}`).then((r) => r.data),
    enabled: !!person,
  });
  const entries = q.data?.timeline || [];
  const { stats, grouped } = useSightings(entries);

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
      <SightingsBody isLoading={q.isLoading} grouped={grouped} emptyLabel="No sightings recorded" />
    </div>
  );
}

// ── Unique people: cluster unknown sightings → count distinct people ─────────
function UniquePeoplePane() {
  const [from, setFrom] = useState(daysAgoISO(7));
  const [to, setTo] = useState(todayISO());
  const [detail, setDetail] = useState(null);
  const q = useQuery({
    queryKey: ["frs-unique-people", from, to],
    queryFn: () => api.get("/frs/tour/unique-people", { params: { since: from, until: to } }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
  const data = q.data || { unique_count: 0, total_sightings: 0, people: [] };
  const dedup = data.total_sightings && data.unique_count ? (data.total_sightings / data.unique_count).toFixed(1) : "—";

  return (
    <div className="rounded-xl border border-card-border bg-card flex flex-col min-h-0 overflow-hidden h-full">
      <div className="px-4 py-3 border-b border-card-border space-y-3 shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-lg bg-amber-500/10 flex items-center justify-center shrink-0"><Icon icon="heroicons-outline:user-group" className="text-amber-500 text-xl" /></div>
            <div>
              <div className="text-sm font-semibold text-foreground">Unique people · unidentified</div>
              <div className="text-[10px] uppercase tracking-wider text-muted">Deduplicated across cameras by face</div>
            </div>
          </div>
          <div className="flex items-center gap-3"><DateInput label="From" value={from} onChange={setFrom} /><DateInput label="To" value={to} onChange={setTo} /></div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Stat icon="heroicons-outline:user-group" label="Unique people" value={data.unique_count} />
          <Stat icon="heroicons-outline:eye" label="Total sightings" value={data.total_sightings} />
          <Stat icon="heroicons-outline:arrows-pointing-in" label="Sightings / person" value={dedup} />
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {q.isLoading ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : !data.people.length ? (
          <EmptyState icon="heroicons-outline:user-group" title="No unidentified people" subtitle="No unknown sightings in this range." />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6 gap-3">
            {data.people.map((p, i) => (
              <button key={i} onClick={() => setDetail(p)} className="text-left rounded-lg border border-card-border overflow-hidden bg-hover/30 hover:border-amber-500/50 transition">
                <div className="relative aspect-square bg-black/30 overflow-hidden">
                  <FaceCrop url={p.snapshot_url} bbox={p.bbox} className="absolute inset-0 h-full w-full" />
                  <span className="absolute top-1 right-1 text-[10px] px-1.5 py-0.5 rounded bg-black/70 text-white font-medium">{p.sightings}×</span>
                </div>
                <div className="p-2">
                  <div className="text-xs text-foreground flex items-center gap-1"><Icon icon="heroicons-outline:video-camera" className="text-muted shrink-0" />{p.camera_count} cam{p.camera_count !== 1 ? "s" : ""}</div>
                  <div className="text-[10px] text-muted truncate">{relative(p.last_seen)}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <Modal open={!!detail} onClose={() => setDetail(null)} title="Unidentified person" wide>
        {detail && (
          <div className="grid gap-4 sm:grid-cols-5">
            <div className="sm:col-span-2 aspect-square rounded-lg bg-black/30 overflow-hidden">
              <FaceCrop url={detail.snapshot_url} bbox={detail.bbox} className="h-full w-full" />
            </div>
            <div className="sm:col-span-3 space-y-2 text-sm">
              {[
                ["Sightings", detail.sightings],
                ["Cameras seen", `${detail.camera_count} — ${(detail.cameras || []).join(", ") || "—"}`],
                ["First seen", detail.first_seen ? fmtTime(detail.first_seen) + " · " + fmtDay(detail.first_seen) : "—"],
                ["Last seen", detail.last_seen ? fmtTime(detail.last_seen) + " · " + fmtDay(detail.last_seen) : "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-card-border pb-1.5"><span className="text-muted">{k}</span><span className="text-foreground text-right">{v}</span></div>
              ))}
              <p className="text-xs text-muted pt-1">This person triggered <strong className="text-foreground">{detail.sightings}</strong> detections across <strong className="text-foreground">{detail.camera_count}</strong> camera(s) — counted once for unique-people analytics.</p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

export default function TourTab() {
  const [view, setView] = useState("poi");
  const [person, setPerson] = useState(null);

  return (
    <div className="flex flex-col h-[calc(100vh-190px)] min-h-[560px]">
      <div className="flex items-center gap-1 mb-3 rounded-lg border border-card-border p-1 w-fit shrink-0">
        {[["poi", "Persons (POI)", "heroicons-outline:user-circle"], ["unique", "Unique people", "heroicons-outline:user-group"]].map(([k, lbl, icon]) => (
          <button key={k} onClick={() => setView(k)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${view === k ? "bg-primary/15 text-foreground font-medium" : "text-muted hover:text-foreground"}`}>
            <Icon icon={icon} />{lbl}
          </button>
        ))}
      </div>

      {view === "poi" ? (
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-10 gap-4">
          <PersonList selectedId={person?.id} onSelect={setPerson} />
          <div className="lg:col-span-7 lg:h-full min-h-[320px] rounded-xl border border-card-border bg-card flex flex-col min-h-0 overflow-hidden">
            <TimelinePane person={person} />
          </div>
        </div>
      ) : (
        <div className="flex-1 min-h-0"><UniquePeoplePane /></div>
      )}
    </div>
  );
}
