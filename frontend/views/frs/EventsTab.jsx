"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { toast } from "sonner";

import { Badge, Button, ConfirmDialog, Input, Modal, Select, Spinner } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

import { EVENT_COLOR, confColor, fmt, pct } from "./shared";

const PAGE = 25;
const TYPE_OPTS = [
  { value: "", label: "All types" },
  { value: "face_recognized", label: "Recognised" },
  { value: "face_unknown", label: "Unknown" },
  { value: "spoof_detected", label: "Spoof" },
  { value: "face_detected", label: "Detected" },
];
const TYPE_LABEL = { face_recognized: "Recognised", face_unknown: "Unknown", spoof_detected: "Spoof", face_detected: "Detected" };

function Thumb({ url, icon = "heroicons-outline:photo", className = "h-10 w-16" }) {
  return (
    <div className={`${className} rounded bg-black/40 border border-card-border overflow-hidden flex items-center justify-center shrink-0`}>
      {url ? <img src={fileUrl(url)} alt="" loading="lazy" className="h-full w-full object-cover" /> : <Icon icon={icon} className="text-muted" />}
    </div>
  );
}

export default function EventsTab() {
  const qc = useQueryClient();
  const [page, setPage] = useState(0);
  const [type, setType] = useState("");
  const [camera, setCamera] = useState("");
  const [personId, setPersonId] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [detail, setDetail] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const cams = useQuery({ queryKey: ["frs-cameras"], queryFn: () => api.get("/frs/cameras").then((r) => r.data) });

  const params = useMemo(() => {
    const p = { limit: PAGE, offset: page * PAGE };
    if (type) p.event_type = type;
    if (camera) p.camera_id = camera;
    if (personId.trim()) p.person_id = personId.trim();
    if (since) p.since = new Date(since).toISOString();
    if (until) p.until = new Date(until).toISOString();
    return p;
  }, [page, type, camera, personId, since, until]);

  const events = useQuery({
    queryKey: ["frs-events", params],
    queryFn: () => api.get("/frs/events", { params }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["frs-events"] });
  const feedback = useMutation({
    mutationFn: ({ event_id, is_correct }) => api.post("/frs/feedback", { event_id, is_correct }),
    onSuccess: (_r, v) => { toast.success(v.is_correct ? "Marked correct" : "Marked wrong"); setDetail((d) => d && { ...d, feedback: v.is_correct ? "correct" : "wrong" }); refresh(); },
    onError: (e) => toast.error(apiError(e)),
  });
  const remove = useMutation({
    mutationFn: (id) => api.delete(`/frs/events/${id}`),
    onSuccess: () => { toast.success("Event deleted"); setDetail(null); setConfirm(null); refresh(); },
    onError: (e) => toast.error(apiError(e)),
  });
  const bulkDelete = useMutation({
    mutationFn: (ids) => api.post("/frs/events/delete", { ids }),
    onSuccess: (r) => { toast.success(`Deleted ${r.data?.deleted ?? "selected"} events`); setSelected(new Set()); setConfirm(null); refresh(); },
    onError: (e) => toast.error(apiError(e)),
  });

  const data = events.data;
  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE));

  const camOpts = [{ value: "", label: "All cameras" }, ...(cams.data || []).map((c) => ({ value: c.id, label: c.name }))];
  const hasFilters = type || camera || personId.trim() || since || until;
  const onFilter = (setter) => (v) => { setter(v); setPage(0); };

  const allSelected = items.length > 0 && items.every((e) => selected.has(e.id));
  const toggle = (id) => setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected((prev) => { const n = new Set(prev); allSelected ? items.forEach((e) => n.delete(e.id)) : items.forEach((e) => n.add(e.id)); return n; });

  function resetFilters() { setType(""); setCamera(""); setPersonId(""); setSince(""); setUntil(""); setPage(0); }

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-card-border bg-card p-3">
        <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted mr-1"><Icon icon="heroicons-outline:funnel" /> Filters</div>
        <div className="w-44"><Select options={camOpts} value={camera} onChange={(e) => onFilter(setCamera)(e.target.value)} placeholder="Camera" /></div>
        <div className="w-40"><Select options={TYPE_OPTS} value={type} onChange={(e) => onFilter(setType)(e.target.value)} placeholder="Type" /></div>
        <div className="w-44"><Input placeholder="Person ID" value={personId} onChange={(e) => { setPersonId(e.target.value); setPage(0); }} /></div>
        <div><span className="block text-[10px] uppercase tracking-wider text-muted mb-0.5">From</span><Input type="datetime-local" value={since} onChange={(e) => { setSince(e.target.value); setPage(0); }} /></div>
        <div><span className="block text-[10px] uppercase tracking-wider text-muted mb-0.5">To</span><Input type="datetime-local" value={until} onChange={(e) => { setUntil(e.target.value); setPage(0); }} /></div>
        {hasFilters && <Button variant="ghost" icon="heroicons-outline:x-mark" onClick={resetFilters}>Clear</Button>}
        {selected.size > 0 && (
          <Button variant="ghost" icon="heroicons-outline:trash" className="text-red-500" disabled={bulkDelete.isPending}
            onClick={() => setConfirm({ title: `Delete ${selected.size} event(s)?`, message: "This permanently removes the selected events and their snapshots.", confirmLabel: "Delete", onConfirm: () => bulkDelete.mutate(Array.from(selected)) })}>
            Delete {selected.size}
          </Button>
        )}
        <div className="ml-auto text-xs text-muted self-center flex items-center gap-2">
          {total} event{total === 1 ? "" : "s"}
          {events.isFetching && <Spinner className="h-3 w-3" />}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-card-border bg-card overflow-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-muted border-b border-card-border">
              <th className="px-3 py-2.5 w-8"><input type="checkbox" checked={allSelected} onChange={toggleAll} className="cursor-pointer align-middle" /></th>
              <th className="px-3 py-2.5 font-medium">Time</th>
              <th className="px-3 py-2.5 font-medium">Camera</th>
              <th className="px-3 py-2.5 font-medium">Type</th>
              <th className="px-3 py-2.5 font-medium">Person / Conf.</th>
              <th className="px-3 py-2.5 font-medium">Face</th>
              <th className="px-3 py-2.5 font-medium">Match</th>
              <th className="px-3 py-2.5 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {events.isLoading ? (
              <tr><td colSpan={8} className="px-3 py-16 text-center"><Spinner /></td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-16 text-center">
                <Icon icon="heroicons-outline:face-smile" className="text-4xl mx-auto text-muted mb-2" />
                <p className="text-sm text-foreground">No recognition events</p>
                <p className="text-xs text-muted mt-1">{hasFilters ? "Try widening your filters." : "Events appear here as faces are recognised."}</p>
              </td></tr>
            ) : (
              items.map((e) => (
                <tr key={e.id} onClick={() => setDetail(e)} className="border-b border-card-border last:border-0 hover:bg-hover transition cursor-pointer">
                  <td className="px-3 py-2" onClick={(ev) => ev.stopPropagation()}><input type="checkbox" checked={selected.has(e.id)} onChange={() => toggle(e.id)} className="cursor-pointer align-middle" /></td>
                  <td className="px-3 py-2 text-muted whitespace-nowrap">{fmt(e.triggered_at)}</td>
                  <td className="px-3 py-2 text-muted">{e.camera_name || "—"}</td>
                  <td className="px-3 py-2"><Badge color={EVENT_COLOR[e.event_type] || "slate"}>{TYPE_LABEL[e.event_type] || e.event_type}</Badge></td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="text-foreground truncate max-w-[140px]">{e.person_name || "Unknown"}</span>
                      {e.confidence != null && <span className={`text-xs tabular-nums text-${confColor(e.confidence)}-500`}>{pct(e.confidence)}</span>}
                    </div>
                  </td>
                  <td className="px-3 py-2"><Thumb url={e.snapshot_url} /></td>
                  <td className="px-3 py-2"><Thumb url={e.match_thumb_url} icon="heroicons-outline:user" className="h-10 w-10" /></td>
                  <td className="px-3 py-2 text-right whitespace-nowrap" onClick={(ev) => ev.stopPropagation()}>
                    {e.feedback && <Icon icon={e.feedback === "correct" ? "heroicons-solid:check-circle" : "heroicons-solid:x-circle"} className={`inline mr-2 ${e.feedback === "correct" ? "text-green-500" : "text-red-500"}`} />}
                    <button title="Delete" className="p-1.5 text-red-500 hover:text-red-400" onClick={() => setConfirm({ title: "Delete this event?", message: "This removes the event and its snapshot.", confirmLabel: "Delete", onConfirm: () => remove.mutate(e.id) })}><Icon icon="heroicons-outline:trash" /></button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <span className="text-muted">Page {page + 1} / {totalPages}</span>
          <Button variant="secondary" icon="heroicons-outline:chevron-left" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} />
          <Button variant="secondary" icon="heroicons-outline:chevron-right" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)} />
        </div>
      )}

      {/* Detail modal */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title="Event details" wide
        footer={detail && <>
          <Button variant="ghost" icon="heroicons-outline:trash" className="text-red-500" onClick={() => setConfirm({ title: "Delete this event?", message: "This removes the event and its snapshot.", confirmLabel: "Delete", onConfirm: () => remove.mutate(detail.id) })}>Delete</Button>
          <div className="flex-1" />
          {detail.person_id && <>
            <Button variant={detail.feedback === "wrong" ? "danger" : "secondary"} icon="heroicons-outline:x-mark" disabled={feedback.isPending} onClick={() => feedback.mutate({ event_id: detail.id, is_correct: false })}>Wrong</Button>
            <Button variant={detail.feedback === "correct" ? "success" : "secondary"} icon="heroicons-outline:check" disabled={feedback.isPending} onClick={() => feedback.mutate({ event_id: detail.id, is_correct: true })}>Correct</Button>
          </>}
        </>}>
        {detail && (
          <div className="grid md:grid-cols-5 gap-4 items-stretch">
            <div className="md:col-span-3 flex flex-col">
              <div className="text-[10px] uppercase tracking-wider text-muted mb-1.5">Snapshot</div>
              <div className="flex-1 min-h-[240px] rounded-lg bg-black/40 border border-card-border overflow-hidden flex items-center justify-center">
                {detail.snapshot_url ? <img src={fileUrl(detail.snapshot_url)} alt="" className="h-full w-full object-contain" /> : <Icon icon="heroicons-outline:photo" className="text-4xl text-muted" />}
              </div>
            </div>
            <div className="md:col-span-2 flex flex-col gap-3">
              <div className="flex gap-3">
                <div className="flex-1">
                  <div className="text-[10px] uppercase tracking-wider text-muted mb-1.5">Detected face</div>
                  <div className="aspect-square rounded-lg bg-black/40 border border-card-border overflow-hidden flex items-center justify-center">
                    {detail.snapshot_url ? <img src={fileUrl(detail.snapshot_url)} alt="" className="h-full w-full object-cover" /> : <Icon icon="heroicons-outline:face-frown" className="text-2xl text-muted" />}
                  </div>
                </div>
                {detail.match_thumb_url && (
                  <div className="flex-1">
                    <div className="text-[10px] uppercase tracking-wider text-blue-400 mb-1.5">Matched POI</div>
                    <div className="aspect-square rounded-lg bg-black/40 border border-card-border overflow-hidden flex items-center justify-center">
                      <img src={fileUrl(detail.match_thumb_url)} alt="" className="h-full w-full object-cover" />
                    </div>
                  </div>
                )}
              </div>
              <dl className="grid grid-cols-[84px_1fr] gap-x-3 gap-y-2 text-sm items-center">
                <Row label="Type"><Badge color={EVENT_COLOR[detail.event_type] || "slate"}>{TYPE_LABEL[detail.event_type] || detail.event_type}</Badge></Row>
                <Row label="Person">{detail.person_name || "Unknown"}</Row>
                <Row label="Camera">{detail.camera_name || "—"}</Row>
                <Row label="Confidence"><span className={`text-${confColor(detail.confidence)}-500`}>{pct(detail.confidence)}</span></Row>
                {detail.gender && <Row label="Gender">{detail.gender}{detail.gender_confidence != null ? ` (${pct(detail.gender_confidence)})` : ""}</Row>}
                {detail.age_range && <Row label="Age">{detail.age_range}</Row>}
                {detail.liveness_score != null && <Row label="Liveness">{pct(detail.liveness_score)}</Row>}
                {detail.track_id && <Row label="Track">{detail.track_id}</Row>}
                <Row label="Time">{fmt(detail.triggered_at)}</Row>
                {detail.feedback && <Row label="Verdict"><Badge color={detail.feedback === "correct" ? "green" : "red"}>{detail.feedback}</Badge></Row>}
              </dl>
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={remove.isPending || bulkDelete.isPending} />
    </div>
  );
}

function Row({ label, children }) {
  return (
    <>
      <dt className="text-[10px] uppercase tracking-wider text-muted self-center">{label}</dt>
      <dd className="min-w-0 text-foreground break-words">{children}</dd>
    </>
  );
}
