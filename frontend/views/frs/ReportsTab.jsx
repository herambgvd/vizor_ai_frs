"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, EmptyState, Input, Select, Spinner } from "@/web/kit";
import { api, apiError } from "@/web/api";

import { fmt } from "./shared";

const REPORTS = [
  { key: "attendance", label: "Attendance", icon: "heroicons-outline:calendar-days", desc: "Per-person daily presence" },
  { key: "group", label: "Group", icon: "heroicons-outline:user-group", desc: "Sightings per group" },
  { key: "mismatch", label: "Mismatch", icon: "heroicons-outline:exclamation-triangle", desc: "Low-confidence recognitions" },
  { key: "unknown", label: "Unknown", icon: "heroicons-outline:question-mark-circle", desc: "Unidentified faces" },
];
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const SCHED_EMPTY = { name: "", report: "attendance", fmt: "xlsx", frequency: "daily", at_time: "08:00", range_days: 7, recipients: "" };

export default function ReportsTab() {
  const qc = useQueryClient();
  const [report, setReport] = useState("attendance");
  const [from, setFrom] = useState(daysAgo(7));
  const [to, setTo] = useState(today());
  const [showSched, setShowSched] = useState(false);
  const [sched, setSched] = useState(SCHED_EMPTY);

  const data = useQuery({
    queryKey: ["frs-report", report, from, to],
    queryFn: () => api.get(`/frs/reports/${report}`, { params: { day_from: from, day_to: to } }).then((r) => r.data),
  });
  const schedules = useQuery({ queryKey: ["frs-report-schedules"], queryFn: () => api.get("/frs/report-schedules").then((r) => r.data.items) });
  const runs = useQuery({ queryKey: ["frs-report-runs"], queryFn: () => api.get("/frs/report-runs").then((r) => r.data.items) });

  function exportFile(format) {
    api.get(`/frs/reports/${report}/export`, { params: { format, day_from: from, day_to: to }, responseType: "blob" })
      .then((r) => { const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = `${report}-${to}.${format}`; a.click(); URL.revokeObjectURL(u); })
      .catch((e) => toast.error(apiError(e)));
  }

  const createSched = useMutation({
    mutationFn: (b) => api.post("/frs/report-schedules", b),
    onSuccess: () => { toast.success("Schedule added"); qc.invalidateQueries({ queryKey: ["frs-report-schedules"] }); setSched(SCHED_EMPTY); },
    onError: (e) => toast.error(apiError(e)),
  });
  const delSched = useMutation({ mutationFn: (id) => api.delete(`/frs/report-schedules/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["frs-report-schedules"] }) });
  const runSched = useMutation({ mutationFn: (id) => api.post(`/frs/report-schedules/${id}/run`), onSuccess: () => { toast.success("Report generated"); qc.invalidateQueries({ queryKey: ["frs-report-runs"] }); } });
  function downloadRun(id, fname) { api.get(`/frs/report-runs/${id}/download`, { responseType: "blob" }).then((r) => { const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = fname; a.click(); URL.revokeObjectURL(u); }); }

  const cols = data.data?.columns || [];
  const items = data.data?.items || [];

  return (
    <div className="space-y-6">
      {/* selector */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {REPORTS.map((r) => (
          <button key={r.key} onClick={() => setReport(r.key)} className={`text-left rounded-xl border p-4 transition ${report === r.key ? "border-foreground bg-hover" : "border-card-border hover:border-muted"}`}>
            <Icon icon={r.icon} className="text-xl text-foreground mb-2" />
            <div className="text-sm font-medium text-foreground">{r.label}</div>
            <div className="text-xs text-muted mt-0.5">{r.desc}</div>
          </button>
        ))}
      </div>

      {/* range + export */}
      <div className="flex flex-wrap items-end gap-3">
        <Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" />
        <Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" />
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" icon="heroicons-outline:document-text" onClick={() => exportFile("csv")}>CSV</Button>
          <Button variant="secondary" icon="heroicons-outline:table-cells" onClick={() => exportFile("xlsx")}>Excel</Button>
        </div>
      </div>

      {/* table */}
      <Card className="p-0 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-card-border flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground capitalize">{report} report</span>
          <span className="text-xs text-muted">{items.length} rows{data.isFetching ? " · loading…" : ""}</span>
        </div>
        {data.isLoading ? (
          <div className="flex justify-center py-12"><Spinner /></div>
        ) : items.length === 0 ? (
          <div className="py-10"><EmptyState icon="heroicons-outline:document-chart-bar" title="No data" subtitle="No rows for this range." /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-card-border text-left text-muted">{cols.map((c) => <th key={c} className="px-4 py-2 font-medium capitalize">{c.replace(/_/g, " ")}</th>)}</tr></thead>
              <tbody>
                {items.map((row, i) => (
                  <tr key={i} className="border-b border-card-border last:border-0">
                    {cols.map((c) => <td key={c} className="px-4 py-2 text-foreground">{typeof row[c] === "number" && c === "confidence" ? `${Math.round(row[c] * 100)}%` : (row[c] ?? "—")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* scheduled reports */}
      <Card className="p-0">
        <button onClick={() => setShowSched((s) => !s)} className="w-full flex items-center justify-between px-4 py-3">
          <span className="flex items-center gap-2 text-sm font-semibold text-foreground"><Icon icon="heroicons-outline:calendar" /> Scheduled reports</span>
          <Icon icon={showSched ? "heroicons-outline:chevron-up" : "heroicons-outline:chevron-down"} className="text-muted" />
        </button>
        {showSched && (
          <div className="px-4 pb-4 space-y-4 border-t border-card-border pt-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
              <Input label="Name" value={sched.name} onChange={(e) => setSched({ ...sched, name: e.target.value })} placeholder="Daily attendance" />
              <Select label="Report" options={REPORTS.map((r) => ({ value: r.key, label: r.label }))} value={sched.report} onChange={(e) => setSched({ ...sched, report: e.target.value })} />
              <Select label="Format" options={[{ value: "xlsx", label: "XLSX" }, { value: "csv", label: "CSV" }]} value={sched.fmt} onChange={(e) => setSched({ ...sched, fmt: e.target.value })} />
              <Select label="Frequency" options={[{ value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }, { value: "monthly", label: "Monthly" }]} value={sched.frequency} onChange={(e) => setSched({ ...sched, frequency: e.target.value })} />
              <Input label="Time" type="time" value={sched.at_time} onChange={(e) => setSched({ ...sched, at_time: e.target.value })} />
              <Input label="Range days" type="number" value={sched.range_days} onChange={(e) => setSched({ ...sched, range_days: Number(e.target.value) || 7 })} />
              <Input label="Recipients" value={sched.recipients} onChange={(e) => setSched({ ...sched, recipients: e.target.value })} placeholder="a@x.com, b@y.com" />
            </div>
            <Button variant="success" icon="heroicons-outline:plus" disabled={!sched.name || createSched.isPending} onClick={() => createSched.mutate(sched)}>Add schedule</Button>

            {schedules.data?.length > 0 && (
              <ul className="divide-y divide-card-border">
                {schedules.data.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-foreground">{s.name}</div>
                      <div className="text-xs text-muted">{s.report} · {s.frequency} at {s.at_time} · {s.fmt.toUpperCase()}{s.recipients ? ` · ${s.recipients}` : ""}</div>
                    </div>
                    <span className="text-xs text-muted hidden sm:block">next {fmt(s.next_run_at)}</span>
                    <button title="Run now" onClick={() => runSched.mutate(s.id)} className="p-1.5 text-blue-400 hover:text-blue-300"><Icon icon="heroicons-outline:play" /></button>
                    <button title="Delete" onClick={() => delSched.mutate(s.id)} className="p-1.5 text-red-500 hover:text-red-400"><Icon icon="heroicons-outline:trash" /></button>
                  </li>
                ))}
              </ul>
            )}

            {runs.data?.length > 0 && (
              <div>
                <div className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">Recent runs</div>
                <ul className="divide-y divide-card-border">
                  {runs.data.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
                      <span className="capitalize text-foreground">{r.report}</span>
                      <span className="text-xs text-muted">{r.rows} rows · {fmt(r.created_at)}</span>
                      <Badge color={r.email_ok ? "green" : "slate"}>{r.emailed_to ? (r.email_ok ? "emailed" : "email failed") : "no email"}</Badge>
                      <button onClick={() => downloadRun(r.id, r.filename)} className="ml-auto text-blue-400 hover:underline text-xs">Download</button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
