"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, EmptyState, Input, Modal, Spinner } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

const PAGE_SIZE = 25;
const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function fmtDur(sec) {
  if (sec == null) return "—";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
function downloadCsv(name, rows) {
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

// small date input styled for the dark theme
function DateInput({ value, onChange, label }) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      {label}
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-field bg-transparent px-2.5 py-1.5 text-sm text-foreground outline-none focus:border-muted" />
    </label>
  );
}

function Thumb({ url, time }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-9 w-9 rounded-md overflow-hidden bg-black/40 shrink-0 flex items-center justify-center">
        {url ? <img src={fileUrl(url)} alt="" className="h-full w-full object-cover" />
          : <Icon icon="heroicons-outline:user" className="text-muted text-sm" />}
      </div>
      <span className={time === "—" ? "text-muted" : "text-foreground"}>{time}</span>
    </div>
  );
}

// ── Log view ──────────────────────────────────────────────────────────────
function LogView() {
  const qc = useQueryClient();
  const [since, setSince] = useState(daysAgoISO(7));
  const [until, setUntil] = useState(todayISO());
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState(null);
  const [delTarget, setDelTarget] = useState(null); // attendance row pending delete
  const [pw, setPw] = useState("");

  const q = useQuery({
    queryKey: ["frs-attendance", since, until, page],
    queryFn: () => api.get("/frs/attendance", { params: { since, until, page, page_size: PAGE_SIZE } }).then((r) => r.data),
    keepPreviousData: true,
  });
  const data = q.data || { items: [], total: 0, pages: 1 };

  // Deleting an attendance record is a sensitive action — the operator must
  // re-enter their password (verified server-side) to confirm.
  const del = useMutation({
    mutationFn: ({ id, password }) => api.delete(`/frs/attendance/${id}`, { data: { password } }),
    onSuccess: () => {
      toast.success("Attendance record deleted");
      qc.invalidateQueries({ queryKey: ["frs-attendance"] });
      setDelTarget(null); setPw("");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const exportCsv = () => {
    const rows = [["Person", "Day", "Check-in", "Check-out", "Duration"]];
    data.items.forEach((a) => rows.push([a.person_name || "—", a.day, fmtTime(a.check_in_at), fmtTime(a.check_out_at), fmtDur(a.duration_seconds)]));
    downloadCsv(`attendance_${since}_${until}.csv`, rows);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <DateInput label="From" value={since} onChange={(v) => { setSince(v); setPage(1); }} />
          <DateInput label="To" value={until} onChange={(v) => { setUntil(v); setPage(1); }} />
        </div>
        <Button variant="secondary" icon="heroicons-outline:arrow-down-tray" onClick={exportCsv} disabled={!data.items.length}>Export CSV</Button>
      </div>

      {q.isLoading ? <div className="flex justify-center py-20"><Spinner /></div>
        : !data.items.length ? <EmptyState icon="heroicons-outline:calendar-days" title="No attendance" subtitle="No check-ins in this range." />
        : (
          <div className="rounded-xl border border-card-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-hover/40 text-muted text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left font-medium px-4 py-2.5">Person</th>
                  <th className="text-left font-medium px-4 py-2.5">Day</th>
                  <th className="text-left font-medium px-4 py-2.5">Check-in</th>
                  <th className="text-left font-medium px-4 py-2.5">Check-out</th>
                  <th className="text-left font-medium px-4 py-2.5">Duration</th>
                  <th className="px-4 py-2.5 w-10" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((a, i) => (
                  <tr key={a.id || i} onClick={() => setDetail(a)} className="group border-t border-card-border hover:bg-hover/40 cursor-pointer">
                    <td className="px-4 py-2.5 font-medium text-foreground">{a.person_name || "—"}</td>
                    <td className="px-4 py-2.5 text-muted">{a.day}</td>
                    <td className="px-4 py-2.5"><Thumb url={a.check_in_url} time={fmtTime(a.check_in_at)} /></td>
                    <td className="px-4 py-2.5"><Thumb url={a.check_out_url} time={fmtTime(a.check_out_at)} /></td>
                    <td className="px-4 py-2.5 text-foreground">{fmtDur(a.duration_seconds)}</td>
                    <td className="px-2 py-2.5 text-right">
                      <button
                        title="Delete record"
                        onClick={(e) => { e.stopPropagation(); setPw(""); setDelTarget(a); }}
                        className="p-1.5 rounded text-muted opacity-0 group-hover:opacity-100 hover:text-red-500 transition"
                      >
                        <Icon icon="heroicons-outline:trash" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {data.pages > 1 && (
        <div className="flex items-center justify-between mt-3 text-sm text-muted">
          <span>{data.total} records · page {page} / {data.pages}</span>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
            <Button variant="secondary" disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? `${detail.person_name || "Unknown"} · ${detail.day}` : ""}>
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              {[["Check-in", detail.check_in_url, detail.check_in_at], ["Check-out", detail.check_out_url, detail.check_out_at]].map(([lbl, url, at]) => (
                <div key={lbl}>
                  <div className="text-xs text-muted mb-1">{lbl} · {fmtTime(at)}</div>
                  <div className="aspect-square rounded-lg overflow-hidden bg-black/40 flex items-center justify-center">
                    {url ? <img src={fileUrl(url)} alt="" className="h-full w-full object-cover" /> : <Icon icon="heroicons-outline:user" className="text-3xl text-muted" />}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between text-sm border-t border-card-border pt-3">
              <span className="text-muted">Duration</span><span className="font-medium text-foreground">{fmtDur(detail.duration_seconds)}</span>
            </div>
          </div>
        )}
      </Modal>

      {/* Password-confirmed delete */}
      <Modal
        open={!!delTarget}
        onClose={() => { if (!del.isPending) { setDelTarget(null); setPw(""); } }}
        title="Delete attendance record"
        footer={
          <>
            <Button variant="secondary" onClick={() => { setDelTarget(null); setPw(""); }} disabled={del.isPending}>Cancel</Button>
            <Button variant="danger" disabled={!pw || del.isPending} onClick={() => del.mutate({ id: delTarget.id, password: pw })}>
              {del.isPending ? "Deleting…" : "Delete"}
            </Button>
          </>
        }
      >
        {delTarget && (
          <div className="space-y-3">
            <p className="text-sm text-muted">
              Delete the attendance record for <strong className="text-foreground">{delTarget.person_name || "Unknown"}</strong> on {delTarget.day}? This cannot be undone.
            </p>
            <Input
              type="password"
              label="Confirm with your password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="Your account password"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter" && pw && !del.isPending) del.mutate({ id: delTarget.id, password: pw }); }}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}

// ── Report view ────────────────────────────────────────────────────────────
function ReportView() {
  const [from, setFrom] = useState(daysAgoISO(30));
  const [to, setTo] = useState(todayISO());
  const q = useQuery({
    queryKey: ["frs-attendance-report", from, to],
    queryFn: () => api.get("/frs/attendance/report", { params: { day_from: from, day_to: to } }).then((r) => r.data),
  });
  const data = q.data || { items: [] };
  const totalDays = useMemo(() => {
    const d = (new Date(to) - new Date(from)) / 864e5;
    return Math.max(1, Math.round(d) + 1);
  }, [from, to]);

  const exportCsv = () => {
    const rows = [["Person", "Days present", "Total days", "First seen", "Last seen"]];
    data.items.forEach((r) => rows.push([r.person_name, r.days_present, totalDays, r.first_seen, r.last_seen]));
    downloadCsv(`attendance_report_${from}_${to}.csv`, rows);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <DateInput label="From" value={from} onChange={setFrom} />
          <DateInput label="To" value={to} onChange={setTo} />
        </div>
        <Button variant="secondary" icon="heroicons-outline:arrow-down-tray" onClick={exportCsv} disabled={!data.items.length}>Export CSV</Button>
      </div>
      {q.isLoading ? <div className="flex justify-center py-20"><Spinner /></div>
        : !data.items.length ? <EmptyState icon="heroicons-outline:chart-bar" title="No data" subtitle="No attendance in this range." />
        : (
          <div className="rounded-xl border border-card-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-hover/40 text-muted text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left font-medium px-4 py-2.5">Person</th>
                  <th className="text-left font-medium px-4 py-2.5 w-1/3">Days present</th>
                  <th className="text-left font-medium px-4 py-2.5">First seen</th>
                  <th className="text-left font-medium px-4 py-2.5">Last seen</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r, i) => (
                  <tr key={i} className="border-t border-card-border">
                    <td className="px-4 py-2.5 font-medium text-foreground">{r.person_name}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-hover overflow-hidden">
                          <div className="h-full bg-green-500" style={{ width: `${Math.min(100, (r.days_present / totalDays) * 100)}%` }} />
                        </div>
                        <span className="text-xs text-muted w-14 text-right">{r.days_present}/{totalDays}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-muted">{r.first_seen}</td>
                    <td className="px-4 py-2.5 text-muted">{r.last_seen}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}

export default function AttendanceTab() {
  const [view, setView] = useState("log");
  return (
    <div>
      <div className="flex items-center gap-1 mb-4 rounded-lg border border-card-border p-1 w-fit">
        {[["log", "Log", "heroicons-outline:list-bullet"], ["report", "Report", "heroicons-outline:chart-bar"]].map(([k, lbl, icon]) => (
          <button key={k} onClick={() => setView(k)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${view === k ? "bg-primary/15 text-foreground font-medium" : "text-muted hover:text-foreground"}`}>
            <Icon icon={icon} />{lbl}
          </button>
        ))}
      </div>
      {view === "log" ? <LogView /> : <ReportView />}
    </div>
  );
}
