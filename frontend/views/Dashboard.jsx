"use client";

// FRS operations overview — the authenticated home view. KPI row from the
// /frs/reports/summary endpoint, a live recognitions feed (5s poll), and a
// cameras strip. Matches the FRS tabs' visual language (cards, muted text, kit
// Badge/Spinner) and stays resilient if the summary endpoint hasn't yet been
// enhanced with the per-day fields (falls back to the all-time counters).

import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import Link from "next/link";

import { PageHeader, Spinner } from "@/web/kit";
import { api, fileUrl } from "@/web/api";
import { useAuth } from "@/web/auth";

import { CAM_STATUS_COLOR, EVENT_COLOR, fmtTime, pct } from "./frs/shared";

const TYPE_LABEL = { face_recognized: "Recognised", face_unknown: "Unknown", spoof_detected: "Spoof", face_detected: "Detected" };

// First defined value — lets the KPIs read the enhanced per-day field when the
// backend serves it, else fall back to the all-time counter, else a dash.
function pick(...vals) {
  for (const v of vals) if (v != null) return v;
  return null;
}

function KpiCard({ icon, color, label, value, sublabel, loading }) {
  return (
    <div className="rounded-xl border border-card-border bg-card p-4 flex items-center gap-3.5">
      <div className={`h-12 w-12 rounded-full bg-hover flex items-center justify-center shrink-0 ${color}`}>
        <Icon icon={icon} className="text-xl" />
      </div>
      <div className="min-w-0">
        {loading ? (
          <div className="h-7 w-12 rounded bg-hover animate-pulse" />
        ) : (
          <div className="text-2xl font-semibold text-foreground leading-tight tabular-nums">{value ?? "—"}</div>
        )}
        <div className="text-[13px] font-medium text-foreground truncate">{label}</div>
        {sublabel && <div className="text-[11px] text-muted truncate">{sublabel}</div>}
      </div>
    </div>
  );
}

export default function FrsDashboard() {
  const { user } = useAuth();

  const summaryQ = useQuery({
    queryKey: ["frs-summary"],
    queryFn: () => api.get("/frs/reports/summary").then((r) => r.data),
    refetchInterval: 15000,
  });
  const liveQ = useQuery({
    queryKey: ["frs-dash-live"],
    queryFn: () => api.get("/frs/live", { params: { limit: 8 } }).then((r) => r.data.items),
    refetchInterval: 5000,
  });
  const camsQ = useQuery({
    queryKey: ["frs-cameras"],
    queryFn: () => api.get("/frs/cameras").then((r) => r.data),
    refetchInterval: 15000,
  });

  const s = summaryQ.data || {};
  const cameras = camsQ.data || [];
  const feed = liveQ.data || [];

  // Cameras online / total: prefer the summary counters, else derive from the list.
  const camsOnline = pick(s.cameras_online, cameras.filter((c) => c.status === "online").length);
  const camsTotal = pick(s.cameras_total, cameras.length);
  const camsRecognising = pick(s.cameras_recognising, cameras.filter((c) => c.recognition_enabled).length);

  const recognizedToday = pick(s.recognitions_today, s.recognized);
  const unknownsToday = pick(s.unknowns_today, s.unknown);
  const eventsToday = pick(s.events_today, s.total_events);
  const personsEnrolled = pick(s.persons_enrolled, s.persons);
  const personsTotal = pick(s.persons_total, s.persons);

  const kpiLoading = summaryQ.isLoading;
  const totalToday = (Number(recognizedToday) || 0) + (Number(unknownsToday) || 0);
  const recPct = totalToday > 0 ? Math.round(((Number(recognizedToday) || 0) / totalToday) * 100) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome, ${user?.full_name || user?.email || "operator"}`}
        subtitle="Face recognition operations — today's activity, live recognitions and camera health."
      />

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <KpiCard icon="heroicons-outline:check-badge" color="text-green-500" label="Recognitions today"
          value={recognizedToday} sublabel={`${pick(s.recognized, "—")} all-time`} loading={kpiLoading} />
        <KpiCard icon="heroicons-outline:question-mark-circle" color="text-amber-500" label="Unknowns today"
          value={unknownsToday} sublabel={`${pick(s.unknown, "—")} all-time`} loading={kpiLoading} />
        <KpiCard icon="heroicons-outline:video-camera" color="text-blue-400" label="Cameras online"
          value={`${camsOnline ?? "—"} / ${camsTotal ?? "—"}`}
          sublabel={camsRecognising != null ? `${camsRecognising} recognising` : undefined}
          loading={kpiLoading && camsQ.isLoading} />
        <KpiCard icon="heroicons-outline:user-group" color="text-indigo-400" label="Persons enrolled"
          value={personsEnrolled} sublabel={personsTotal != null ? `${personsTotal} total` : undefined} loading={kpiLoading} />
        <KpiCard icon="heroicons-outline:clipboard-document-check" color="text-purple-400" label="Attendance today"
          value={pick(s.attendance_today)} sublabel="present today" loading={kpiLoading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Recent recognitions (live) */}
        <div className="lg:col-span-2 rounded-xl border border-card-border bg-card flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-card-border">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
              <h2 className="text-sm font-semibold text-foreground">Recent recognitions</h2>
              {liveQ.isFetching && <Spinner className="h-3 w-3" />}
            </div>
            <Link href="/events" className="text-xs text-muted hover:text-foreground transition">View all →</Link>
          </div>
          {liveQ.isLoading ? (
            <div className="flex justify-center py-14"><Spinner /></div>
          ) : feed.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-muted py-14 gap-2">
              <Icon icon="heroicons-outline:signal" className="text-3xl" />
              <span className="text-sm">Waiting for recognitions…</span>
            </div>
          ) : (
            <ul className="divide-y divide-card-border">
              {feed.map((e) => {
                const unknown = !e.person_name;
                return (
                  <li key={e.id} className="flex items-center gap-3 px-4 py-2.5">
                    <div className="h-11 w-16 rounded bg-black/40 border border-card-border overflow-hidden shrink-0 flex items-center justify-center">
                      {e.snapshot_url
                        ? <img src={fileUrl(e.snapshot_url)} alt="" loading="lazy" className="h-full w-full object-cover" />
                        : <Icon icon="heroicons-outline:user" className="text-muted" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm truncate ${unknown ? "text-amber-500" : "text-foreground"}`}>
                        {e.person_name || "Unknown"}
                      </div>
                      <div className="text-[11px] text-muted truncate">
                        {e.camera_name || "—"} · {fmtTime(e.triggered_at)}
                      </div>
                    </div>
                    {e.confidence != null && (
                      <span className={`text-xs tabular-nums text-${EVENT_COLOR[e.event_type] || "slate"}-500`}>{pct(e.confidence)}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Events today by type breakdown */}
        <div className="rounded-xl border border-card-border bg-card p-4">
          <h2 className="text-sm font-semibold text-foreground mb-4">Events today</h2>
          <div className="text-3xl font-semibold text-foreground tabular-nums mb-4">{eventsToday ?? "—"}</div>
          {totalToday > 0 ? (
            <>
              <div className="h-2 w-full rounded-full overflow-hidden bg-hover flex mb-3">
                <div className="bg-green-500 h-full" style={{ width: `${recPct}%` }} />
                <div className="bg-amber-500 h-full" style={{ width: `${100 - recPct}%` }} />
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-muted"><span className="h-2.5 w-2.5 rounded-full bg-green-500" />Recognised</span>
                  <span className="tabular-nums text-foreground">{recognizedToday ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-muted"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" />Unknown</span>
                  <span className="tabular-nums text-foreground">{unknownsToday ?? 0}</span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted">No events recorded today yet.</p>
          )}
        </div>
      </div>

      {/* Cameras strip */}
      <div className="rounded-xl border border-card-border bg-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-foreground">Cameras</h2>
          <Link href="/cameras" className="text-xs text-muted hover:text-foreground transition">Manage →</Link>
        </div>
        {camsQ.isLoading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : cameras.length === 0 ? (
          <div className="flex flex-col items-center justify-center text-muted py-8 gap-2">
            <Icon icon="heroicons-outline:video-camera-slash" className="text-3xl" />
            <span className="text-sm">No cameras yet.</span>
            <Link href="/cameras" className="text-xs text-blue-400 hover:underline">Add a camera →</Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2">
            {cameras.map((c) => {
              const online = c.status === "online";
              return (
                <Link key={c.id} href="/cameras"
                  className="rounded-lg border border-card-border bg-background/40 p-3 transition hover:border-muted">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`h-2 w-2 rounded-full shrink-0 ${online ? "bg-green-500" : c.status === "error" ? "bg-red-500" : "bg-slate-500"}`} />
                    <span className="text-sm text-foreground truncate">{c.name}</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className={`uppercase tracking-wider text-${CAM_STATUS_COLOR[c.status] || "slate"}-500`}>{c.status}</span>
                    <span className={c.recognition_enabled ? "text-green-500" : "text-muted"}>
                      {c.recognition_enabled ? "FRS on" : "FRS off"}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
