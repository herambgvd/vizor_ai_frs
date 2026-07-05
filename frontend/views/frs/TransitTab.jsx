"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { toast } from "sonner";

import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, Modal, Spinner, Table, Toggle } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

import { fmt, fmtDuration, SESSION_COLOR } from "./shared";

export default function TransitTab() {
  const [sub, setSub] = useState("sessions");
  const rulesQ = useQuery({ queryKey: ["frs-transit-rules"], queryFn: () => api.get("/frs/transit/rules").then((r) => r.data.rules) });
  return (
    <div>
      <div className="flex items-center gap-1 mb-4">
        {[["sessions", "Sessions"], ["rules", `Rules${rulesQ.data ? ` · ${rulesQ.data.length}` : ""}`]].map(([k, l]) => (
          <button key={k} onClick={() => setSub(k)} className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${sub === k ? "bg-hover text-foreground" : "text-muted hover:text-foreground"}`}>{l}</button>
        ))}
      </div>
      {sub === "sessions" ? <Sessions rules={rulesQ.data || []} /> : <Rules q={rulesQ} />}
    </div>
  );
}

function Kpi({ label, value, color }) {
  return <Card className="p-4"><div className={`text-2xl font-semibold ${color}`}>{value}</div><div className="text-xs text-muted mt-0.5">{label}</div></Card>;
}

function Sessions({ rules }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState(null);
  const sessions = useQuery({ queryKey: ["frs-transit-sessions", status], queryFn: () => api.get("/frs/transit/sessions", { params: { status: status || undefined } }).then((r) => r.data.sessions) });
  const sweep = useMutation({ mutationFn: () => api.post("/frs/transit/sweep"), onSuccess: (r) => { toast.success(`${r.data.overdue} flagged overdue`); qc.invalidateQueries({ queryKey: ["frs-transit-sessions"] }); }, onError: (e) => toast.error(apiError(e)) });
  const del = useMutation({ mutationFn: (id) => api.delete(`/frs/transit/sessions/${id}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ["frs-transit-sessions"] }); setDetail(null); }, onError: (e) => toast.error(apiError(e)) });
  const ruleName = (id) => rules.find((r) => r.id === id)?.name || "—";

  const list = sessions.data || [];
  const counts = useMemo(() => ({ open: list.filter((s) => s.status === "open").length, overdue: list.filter((s) => s.status === "overdue").length, closed: list.filter((s) => ["completed", "closed"].includes(s.status)).length }), [list]);

  const cols = [
    { key: "person", label: "Person", render: (s) => <div className="font-medium">{s.person_name || "Unknown"}</div> },
    { key: "rule", label: "Rule", render: (s) => <span className="text-muted">{ruleName(s.rule_id)}</span> },
    { key: "status", label: "Status", render: (s) => <Badge color={SESSION_COLOR[s.status] || "slate"}>{s.status}</Badge> },
    { key: "opened", label: "Opened", render: (s) => <span className="text-muted text-sm">{fmt(s.started_at)}</span> },
    { key: "dur", label: "Duration", render: (s) => <span className="text-muted text-sm">{fmtDuration(s.duration_seconds)}</span> },
    { key: "actions", label: "", render: (s) => <div className="flex justify-end"><button title="Delete" onClick={(e) => { e.stopPropagation(); del.mutate(s.id); }} className="p-1.5 text-red-500 hover:text-red-400"><Icon icon="heroicons-outline:trash" /></button></div> },
  ];

  return (
    <div>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Kpi label="Open" value={counts.open} color="text-amber-500" />
        <Kpi label="Overdue" value={counts.overdue} color="text-red-500" />
        <Kpi label="Closed" value={counts.closed} color="text-green-500" />
      </div>
      <div className="flex items-center gap-1 mb-3">
        {[["", "All"], ["open", "Open"], ["overdue", "Overdue"], ["completed", "Closed"]].map(([k, l]) => (
          <button key={k} onClick={() => setStatus(k)} className={`px-2.5 py-1 rounded text-xs font-medium ${status === k ? "bg-hover text-foreground" : "text-muted hover:text-foreground"}`}>{l}</button>
        ))}
        <Button variant="secondary" icon="heroicons-outline:clock" className="ml-auto" disabled={sweep.isPending} onClick={() => sweep.mutate()}>Sweep overdue</Button>
      </div>
      <Card className="p-2">
        {sessions.isLoading ? <div className="flex justify-center py-12"><Spinner /></div> : (
          <div onClick={(e) => { const tr = e.target.closest?.("[data-id]"); if (tr) setDetail(list.find((s) => s.id === tr.dataset.id)); }}>
            <Table columns={cols.map((c) => c.key === "actions" ? c : { ...c, render: (s) => <span data-id={s.id}>{c.render(s)}</span> })} rows={list} empty={<EmptyState icon="heroicons-outline:map" title="No sessions" subtitle="Sessions appear as persons move between cameras." />} />
          </div>
        )}
      </Card>

      <Modal open={!!detail} onClose={() => setDetail(null)} wide title="Session detail">
        {detail && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2 text-sm">
              {[["Person", detail.person_name || "Unknown"], ["Rule", ruleName(detail.rule_id)], ["Status", detail.status], ["Duration", fmtDuration(detail.duration_seconds)], ["Entry camera", detail.entry_camera || "—"], ["Entry time", fmt(detail.started_at)], ["Exit camera", detail.exit_camera || "— (no exit)"], ["Exit time", fmt(detail.ended_at)]].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-card-border pb-1.5"><span className="text-muted">{k}</span><span className="text-foreground text-right">{v}</span></div>
              ))}
            </div>
            <div className="grid grid-rows-2 gap-3">
              {[["Entry", detail.entry_snapshot], ["Exit", detail.exit_snapshot]].map(([lbl, snap]) => (
                <div key={lbl}>
                  <div className="text-xs text-muted mb-1">{lbl}</div>
                  <div className="aspect-video bg-black/30 rounded-lg overflow-hidden flex items-center justify-center">
                    {snap ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={fileUrl(snap)} alt={lbl} className="max-h-full max-w-full object-contain" />
                    ) : <Icon icon="heroicons-outline:photo" className="text-2xl text-muted" />}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

const RULE_EMPTY = { name: "", entry_camera: "", exit_cameras: "", deadline_minutes: 5, enabled: true };

function Rules({ q }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(RULE_EMPTY);
  const [confirm, setConfirm] = useState(null);

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["frs-transit-rules"] }); setOpen(false); setEditing(null); setForm(RULE_EMPTY); };
  const toBody = (f) => ({ name: f.name, enabled: f.enabled, config: { entry_camera: f.entry_camera, exit_cameras: f.exit_cameras.split(",").map((s) => s.trim()).filter(Boolean), deadline_minutes: Number(f.deadline_minutes) || 0 } });
  const create = useMutation({ mutationFn: (b) => api.post("/frs/transit/rules", b), onSuccess: () => { toast.success("Rule created"); invalidate(); }, onError: (e) => toast.error(apiError(e)) });
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.put(`/frs/transit/rules/${id}`, b), onSuccess: () => { toast.success("Rule updated"); invalidate(); }, onError: (e) => toast.error(apiError(e)) });
  const remove = useMutation({ mutationFn: (id) => api.delete(`/frs/transit/rules/${id}`), onSuccess: () => { toast.success("Rule deleted"); qc.invalidateQueries({ queryKey: ["frs-transit-rules"] }); setConfirm(null); }, onError: (e) => toast.error(apiError(e)) });

  function openCreate() { setEditing(null); setForm(RULE_EMPTY); setOpen(true); }
  function openEdit(r) { setEditing(r); setForm({ name: r.name || "", entry_camera: r.config?.entry_camera || "", exit_cameras: (r.config?.exit_cameras || []).join(", "), deadline_minutes: r.config?.deadline_minutes || 5, enabled: r.enabled }); setOpen(true); }
  const saving = create.isPending || patch.isPending;

  const cols = [
    { key: "name", label: "Name", render: (r) => <div className="font-medium">{r.name}</div> },
    { key: "entry", label: "Entry", render: (r) => <span className="text-muted">{r.config?.entry_camera || "—"}</span> },
    { key: "exits", label: "Exits", render: (r) => <span className="text-muted">{(r.config?.exit_cameras || []).join(", ") || "—"}</span> },
    { key: "window", label: "Window", render: (r) => <span className="text-muted flex items-center gap-1"><Icon icon="heroicons-outline:clock" />{r.config?.deadline_minutes || 0}m</span> },
    { key: "status", label: "Status", render: (r) => <Badge color={r.enabled ? "green" : "slate"}>{r.enabled ? "Enabled" : "Disabled"}</Badge> },
    { key: "actions", label: "", render: (r) => <div className="flex items-center justify-end gap-1"><button title="Edit" onClick={() => openEdit(r)} className="p-1.5 text-muted hover:text-foreground"><Icon icon="heroicons-outline:pencil-square" /></button><button title="Delete" onClick={() => setConfirm({ title: "Delete rule", message: <>Delete <strong>{r.name}</strong>? Its sessions are removed too.</>, confirmLabel: "Delete rule", onConfirm: () => remove.mutate(r.id) })} className="p-1.5 text-red-500 hover:text-red-400"><Icon icon="heroicons-outline:trash" /></button></div> },
  ];

  return (
    <div>
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs text-muted max-w-lg">Define entry→exit camera pairs with a deadline. A person recognized at the entry camera must reach an exit camera within the window — otherwise the session goes overdue.</p>
        <Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>New rule</Button>
      </div>
      <Card className="p-2">
        {q.isLoading ? <div className="flex justify-center py-12"><Spinner /></div> : (
          <Table columns={cols} rows={q.data} empty={<EmptyState icon="heroicons-outline:arrows-right-left" title="No rules" subtitle="Create a transit rule to track movement." />} />
        )}
      </Card>

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? "Edit rule" : "New rule"}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button variant={editing ? "primary" : "success"} disabled={saving || !form.name} onClick={() => { const b = toBody(form); editing ? patch.mutate({ id: editing.id, ...b }) : create.mutate(b); }}>{saving ? "Saving…" : editing ? "Save" : "Create"}</Button></>}>
        <div className="space-y-4">
          <Input label="Rule name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Gate A → Gate B transit" autoFocus />
          <Input label="Entry camera" value={form.entry_camera} onChange={(e) => setForm({ ...form, entry_camera: e.target.value })} placeholder="camera id / name" />
          <Input label="Exit cameras" value={form.exit_cameras} onChange={(e) => setForm({ ...form, exit_cameras: e.target.value })} placeholder="comma-separated" hint="One or more exit cameras" />
          <div className="grid grid-cols-2 gap-4 items-end">
            <Input label="Deadline (minutes)" type="number" value={form.deadline_minutes} onChange={(e) => setForm({ ...form, deadline_minutes: e.target.value })} />
            <div className="flex items-center justify-between rounded-md border border-card-border px-3 py-2.5"><span className="text-sm font-medium text-foreground">Enabled</span><Toggle checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} /></div>
          </div>
        </div>
      </Modal>
      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={remove.isPending} />
    </div>
  );
}
