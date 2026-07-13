"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, ConfirmDialog, EmptyState, Input, Modal, Select, Spinner, Toggle } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

import { CAM_ANALYZE_RES, CAM_DIRECTIONS, CAM_HWACCEL, CAM_STATUS_COLOR } from "./shared";

const round = (n) => Number(n.toFixed(4));

// ── ROI editor ──────────────────────────────────────────────────────────────
// Polygon over the camera's reference snapshot, stored as normalised (0..1)
// [[x,y],...] so it is resolution-independent. Empty = whole frame. Click to add
// a point, drag a corner to move it, Undo/Clear from the toolbar.
function RoiEditor({ value, onChange, bg }) {
  const points = Array.isArray(value) ? value : [];
  const wrapRef = useRef(null);
  const [dragIdx, setDragIdx] = useState(null);

  const toNorm = (e) => {
    const box = wrapRef.current?.getBoundingClientRect();
    if (!box || !box.width || !box.height) return null;
    return [
      round(Math.min(1, Math.max(0, (e.clientX - box.left) / box.width))),
      round(Math.min(1, Math.max(0, (e.clientY - box.top) / box.height))),
    ];
  };
  const addPoint = (e) => { if (dragIdx === null) { const p = toNorm(e); if (p) onChange([...points, p]); } };

  useEffect(() => {
    if (dragIdx === null) return;
    const move = (e) => { const p = toNorm(e); if (p) onChange(points.map((q, i) => (i === dragIdx ? p : q))); };
    const up = () => setDragIdx(null);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [dragIdx, points, onChange]);

  const poly = points.map((p) => `${p[0] * 100},${p[1] * 100}`).join(" ");
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-foreground">Region of interest</span>
        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => onChange(points.slice(0, -1))} disabled={!points.length}
            className="text-xs px-2 py-1 rounded border border-card-border text-muted hover:text-foreground disabled:opacity-40">Undo</button>
          <button type="button" onClick={() => onChange([])} disabled={!points.length}
            className="text-xs px-2 py-1 rounded border border-card-border text-red-500 hover:text-red-400 disabled:opacity-40">Clear</button>
        </div>
      </div>
      <div ref={wrapRef} onClick={addPoint}
        className="relative aspect-video w-full overflow-hidden rounded-lg border border-card-border bg-black/40 cursor-crosshair select-none"
        style={bg ? { backgroundImage: `url(${bg})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
          {points.length > 1 && <polygon points={poly} fill="rgba(34,197,94,0.18)" stroke="#22c55e" strokeWidth="0.4" />}
          {points.map((p, i) => (
            <circle key={i} cx={p[0] * 100} cy={p[1] * 100} r="1.4" fill="#22c55e" stroke="#fff" strokeWidth="0.3"
              className="cursor-move" onMouseDown={(e) => { e.stopPropagation(); setDragIdx(i); }} onClick={(e) => e.stopPropagation()} />
          ))}
        </svg>
        {!bg && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none px-4 text-center">
            <span className="text-xs text-muted">Test the camera to capture a reference frame, then click to draw the ROI.</span>
          </div>
        )}
      </div>
      <p className="text-xs text-muted mt-1.5">{points.length} point{points.length === 1 ? "" : "s"} — click to add · drag a corner to move · empty = whole frame</p>
    </div>
  );
}

function draftOf(c) {
  return {
    name: c.name || "", rtsp_url: c.rtsp_url || "", location: c.location || "", zone: c.zone || "",
    direction: c.direction || "both", hw_accel: c.hw_accel || "none",
    recognition_enabled: !!c.recognition_enabled, enabled: !!c.enabled,
    detection_enabled: !!c.detection_enabled,
    liveness_enabled: c.liveness_enabled ?? true,
    liveness_threshold: c.liveness_threshold ?? 0.7,
    det_conf: c.det_conf ?? 0.5,
    min_confidence: c.min_confidence ?? 0.5,
    min_face_px: c.min_face_px ?? 28,
    min_sharpness: c.min_sharpness ?? 25,
    max_pose_deg: c.max_pose_deg ?? 60,
    dwell_min_frames: c.dwell_min_frames ?? 3,
    alert_suppress_seconds: c.alert_suppress_seconds ?? 300,
    fps: c.fps ?? 10,
    analyze_width: c.analyze_width ?? 0,
    roi: Array.isArray(c.roi) ? c.roi : [],
  };
}

// Small labelled toggle row used inside the config groups.
function ToggleRow({ title, desc, checked, onChange }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-card-border px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{title}</div>
        {desc && <div className="text-xs text-muted mt-0.5">{desc}</div>}
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

// ── Right pane: the selected camera's configuration ───────────────────────────
function CameraConfigPanel({ camera, qc, onDeleted }) {
  const [draft, setDraft] = useState(() => draftOf(camera));
  const [confirmDel, setConfirmDel] = useState(false);
  // Reset only when a DIFFERENT camera is selected, so background polling never
  // clobbers an in-flight edit.
  useEffect(() => { setDraft(draftOf(camera)); }, [camera.id]);

  const patch = useMutation({
    mutationFn: (b) => api.put(`/frs/cameras/${camera.id}`, b),
    onSuccess: () => { toast.success("Camera saved"); qc.invalidateQueries({ queryKey: ["frs-cameras"] }); },
    onError: (e) => toast.error(apiError(e)),
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/frs/cameras/${camera.id}`),
    onSuccess: () => { toast.success("Camera deleted"); qc.invalidateQueries({ queryKey: ["frs-cameras"] }); onDeleted(); },
    onError: (e) => toast.error(apiError(e)),
  });
  const test = useMutation({
    mutationFn: () => api.post(`/frs/cameras/${camera.id}/test`),
    onSuccess: (r) => { r.data.status === "online" ? toast.success("Camera reachable — frame captured") : toast.error(r.data.last_error || "Camera unreachable"); qc.invalidateQueries({ queryKey: ["frs-cameras"] }); },
    onError: (e) => toast.error(apiError(e)),
  });

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const base = draftOf(camera);
  const dirty = JSON.stringify(draft) !== JSON.stringify(base);
  const valid = draft.name.trim() && draft.rtsp_url.trim();
  const RESTART_KEYS = [
    "rtsp_url", "fps", "min_confidence", "detection_enabled", "direction",
    "liveness_enabled", "liveness_threshold", "det_conf", "min_face_px",
    "min_sharpness", "max_pose_deg", "dwell_min_frames", "alert_suppress_seconds",
    "hw_accel", "analyze_width", "roi",
  ];
  const willRestart = draft.recognition_enabled && dirty && RESTART_KEYS.some((k) => JSON.stringify(draft[k]) !== JSON.stringify(base[k]));

  function save() {
    if (!valid) return;
    patch.mutate({
      name: draft.name.trim(), rtsp_url: draft.rtsp_url.trim(), location: draft.location || null, zone: draft.zone || null,
      direction: draft.direction, hw_accel: draft.hw_accel, recognition_enabled: draft.recognition_enabled, enabled: draft.enabled,
      detection_enabled: draft.detection_enabled,
      liveness_enabled: draft.liveness_enabled, liveness_threshold: Number(draft.liveness_threshold),
      det_conf: Number(draft.det_conf), min_confidence: Number(draft.min_confidence),
      min_face_px: Number(draft.min_face_px), min_sharpness: Number(draft.min_sharpness),
      max_pose_deg: Number(draft.max_pose_deg), dwell_min_frames: Number(draft.dwell_min_frames),
      alert_suppress_seconds: Number(draft.alert_suppress_seconds), fps: Number(draft.fps),
      analyze_width: Number(draft.analyze_width),
      roi: Array.isArray(draft.roi) ? draft.roi : [],
    });
  }

  return (
    <div className="rounded-xl border border-card-border bg-card flex flex-col h-full overflow-hidden">
      {/* header */}
      <div className="flex items-center justify-between gap-3 border-b border-card-border p-4 shrink-0">
        <div className="min-w-0">
          <div className="font-semibold text-foreground truncate">{camera.name}</div>
          <div className="flex items-center gap-2 mt-0.5">
            <Badge color={CAM_STATUS_COLOR[camera.status] || "slate"}>{camera.status}</Badge>
            <Badge color={camera.recognition_enabled ? "green" : "slate"}>{camera.recognition_enabled ? "FRS on" : "FRS off"}</Badge>
            {camera.last_error && <span className="text-xs text-red-500 truncate max-w-[240px]" title={camera.last_error}>{camera.last_error}</span>}
          </div>
        </div>
        <Button variant="secondary" icon="heroicons-outline:signal" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending ? "Testing…" : "Test"}
        </Button>
      </div>

      <div className="p-4 grid grid-cols-1 xl:grid-cols-2 gap-x-6 gap-y-5 flex-1 overflow-y-auto">
        {/* left inner column: settings */}
        <div className="space-y-5">
          <section className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Source</h4>
            <Input label="Name" value={draft.name} onChange={(e) => set("name", e.target.value)} />
            <Input label="RTSP URL" value={draft.rtsp_url} onChange={(e) => set("rtsp_url", e.target.value)} placeholder="rtsp://user:pass@host:554/stream" />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Location" value={draft.location} onChange={(e) => set("location", e.target.value)} />
              <Input label="Zone" value={draft.zone} onChange={(e) => set("zone", e.target.value)} />
            </div>
          </section>

          <section className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Recognition</h4>
            <Input label="Match threshold" type="number" step="0.01" min="0.3" max="0.99" value={draft.min_confidence} onChange={(e) => set("min_confidence", e.target.value)}
              hint="Minimum face-match similarity (cosine) to call a recognition. Lower catches tilted/far faces but risks false matches; raise toward 0.6 for stricter security. 0.5 balanced." />
            <ToggleRow title="Recognition" desc="Match faces against the enrolled gallery." checked={draft.recognition_enabled} onChange={(v) => set("recognition_enabled", v)} />
            <ToggleRow title="Detection only" desc="Emit face-detected events without identifying." checked={draft.detection_enabled} onChange={(v) => set("detection_enabled", v)} />
            <Select label="Attendance direction" options={CAM_DIRECTIONS} value={draft.direction} onChange={(e) => set("direction", e.target.value)}
              hint="Entry camera marks check-in, exit camera marks check-out. 'both' = first-seen/last-seen on a single door." />
          </section>

          <section className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Liveness</h4>
            <ToggleRow title="Anti-spoof" checked={draft.liveness_enabled} onChange={(v) => set("liveness_enabled", v)} />
            <Input label="Liveness threshold" type="number" step="0.01" min="0.3" max="0.99" value={draft.liveness_threshold} onChange={(e) => set("liveness_threshold", e.target.value)} />
          </section>

          <section className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Quality</h4>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Detector confidence" type="number" step="0.05" min="0.2" max="0.9" value={draft.det_conf} onChange={(e) => set("det_conf", e.target.value)}
                hint="SCRFD face-detector confidence floor." />
              <Input label="Min face size (px)" type="number" step="4" min="12" max="400" value={draft.min_face_px} onChange={(e) => set("min_face_px", e.target.value)}
                hint="Smaller = catch far/small faces (lower recognition quality)." />
              <Input label="Min sharpness" type="number" step="5" min="0" max="200" value={draft.min_sharpness} onChange={(e) => set("min_sharpness", e.target.value)}
                hint="Reject blurry crops (Laplacian variance)." />
              <Input label="Max pose (deg)" type="number" step="5" min="20" max="90" value={draft.max_pose_deg} onChange={(e) => set("max_pose_deg", e.target.value)}
                hint="Reject faces turned more than this (yaw/pitch)." />
              <Input label="Dwell frames" type="number" step="1" min="1" max="30" value={draft.dwell_min_frames} onChange={(e) => set("dwell_min_frames", e.target.value)}
                hint="Consecutive frames a face must agree before an event fires. Higher = fewer false positives / jitter, slight delay. 3 recommended." />
            </div>
          </section>

          <section className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Alerting</h4>
            <Input label="Alert cooldown (s)" type="number" step="30" min="0" max="3600" value={draft.alert_suppress_seconds} onChange={(e) => set("alert_suppress_seconds", e.target.value)}
              hint="Minimum gap between repeat alerts for the same person." />
          </section>

          <section className="space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Stream</h4>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Analyze FPS" type="number" step="1" min="1" max="15" value={draft.fps} onChange={(e) => set("fps", e.target.value)}
                hint="Frames analysed per second. 10+ recommended — more frames = faster events + steadier recognition." />
              <Select label="Decode" options={CAM_HWACCEL} value={draft.hw_accel} onChange={(e) => set("hw_accel", e.target.value)} />
            </div>
            <Select label="Analyze resolution" options={CAM_ANALYZE_RES} value={String(draft.analyze_width)} onChange={(e) => set("analyze_width", Number(e.target.value))} />
            <p className="text-xs text-muted">
              High-resolution cameras are downscaled for analysis to save CPU — with Decode = NVDEC the resize runs on the GPU.
              The detector is unaffected; 720p–1080p keeps full recognition quality for room-scale cameras.
            </p>
          </section>

          <div className="flex items-center justify-between rounded-md border border-card-border px-3 py-2.5">
            <div><span className="text-sm font-medium text-foreground">Camera enabled</span><div className="text-xs text-muted">Disable to stop streaming without deleting.</div></div>
            <Toggle checked={draft.enabled} onChange={(v) => set("enabled", v)} />
          </div>
        </div>

        {/* right inner column: ROI on the reference frame */}
        <div className="space-y-4">
          <RoiEditor value={draft.roi} onChange={(roi) => set("roi", roi)} bg={camera.snapshot_url ? fileUrl(camera.snapshot_url) : null} />
          {willRestart && (
            <div className="flex items-start gap-2 rounded-md bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
              <Icon icon="heroicons-outline:arrow-path" className="mt-0.5 shrink-0" />
              Changing recognition parameters restarts this camera's worker (a few seconds of downtime) so the new settings take effect.
            </div>
          )}
        </div>
      </div>

      {/* actions */}
      <div className="flex items-center justify-between border-t border-card-border p-4 shrink-0">
        <Button variant="ghost" className="text-red-500 hover:text-red-400" icon="heroicons-outline:trash" onClick={() => setConfirmDel(true)}>Delete</Button>
        <Button variant="primary" disabled={!dirty || !valid || patch.isPending} onClick={save}>{patch.isPending ? "Saving…" : "Save changes"}</Button>
      </div>

      <ConfirmDialog
        state={confirmDel ? { title: "Delete camera", message: <>Delete <strong>{camera.name}</strong>? This removes the camera and stops its worker.</>, confirmLabel: "Delete camera", onConfirm: () => remove.mutate() } : null}
        onClose={() => setConfirmDel(false)} pending={remove.isPending} />
    </div>
  );
}

// ── Cameras tab: 30 / 70 master–detail split ──────────────────────────────────
const EMPTY_CREATE = { name: "", rtsp_url: "", location: "" };

export default function CamerasTab() {
  const qc = useQueryClient();
  const [openCreate, setOpenCreate] = useState(false);
  const [createForm, setCreateForm] = useState(EMPTY_CREATE);
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState("");

  const cams = useQuery({ queryKey: ["frs-cameras"], queryFn: () => api.get("/frs/cameras").then((r) => r.data) });
  const list = cams.data || [];
  const online = list.filter((c) => c.status === "online").length;
  const active = list.filter((c) => c.recognition_enabled).length;

  // Keep a valid selection: default to the first camera; clear if it vanishes.
  useEffect(() => {
    if (!list.length) { if (selectedId) setSelectedId(null); return; }
    if (!list.some((c) => c.id === selectedId)) setSelectedId(list[0].id);
  }, [list, selectedId]);
  const selected = useMemo(() => list.find((c) => c.id === selectedId) || null, [list, selectedId]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? list.filter((c) => `${c.name} ${c.location || ""} ${c.zone || ""}`.toLowerCase().includes(q)) : list;
  }, [list, search]);

  const create = useMutation({
    mutationFn: (b) => api.post("/frs/cameras", b),
    onSuccess: (r) => {
      toast.success("Camera added — configure it to turn recognition on");
      qc.invalidateQueries({ queryKey: ["frs-cameras"] });
      setOpenCreate(false); setCreateForm(EMPTY_CREATE);
      if (r?.data?.id) setSelectedId(r.data.id);
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const createValid = createForm.name.trim() && createForm.rtsp_url.trim();

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-muted">
          Cameras · {list.length}
          {list.length > 0 && <> · <span className="text-green-500">{online} online</span> · <span className="text-foreground">{active} recognising</span></>}
        </div>
        <Button variant="success" icon="heroicons-outline:plus" onClick={() => { setCreateForm(EMPTY_CREATE); setOpenCreate(true); }}>Add camera</Button>
      </div>

      {cams.isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : list.length === 0 ? (
        <EmptyState icon="heroicons-outline:video-camera" title="No cameras yet" subtitle="Add an RTSP source, then configure it and turn recognition on." action={<Button variant="success" icon="heroicons-outline:plus" onClick={() => setOpenCreate(true)}>Add camera</Button>} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[2fr_8fr] gap-4 lg:h-[calc(100vh-200px)]">
          {/* LEFT 20% — camera list */}
          <div className="rounded-xl border border-card-border bg-card overflow-hidden flex flex-col lg:h-full min-h-[280px]">
            <div className="p-2.5 border-b border-card-border shrink-0">
              <div className="relative">
                <Icon icon="heroicons-outline:magnifying-glass" className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted text-sm" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search cameras"
                  className="w-full rounded-md border border-field bg-transparent pl-8 pr-2 py-1.5 text-sm text-foreground placeholder:text-muted outline-none transition focus:border-muted" />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {filtered.length === 0 ? (
                <div className="px-3 py-8 text-center text-xs text-muted">No cameras match “{search}”.</div>
              ) : filtered.map((c) => {
                const sel = c.id === selectedId;
                return (
                  <button key={c.id} onClick={() => setSelectedId(c.id)}
                    className={`w-full text-left flex gap-3 items-center px-3 py-2.5 border-b border-card-border/60 transition ${sel ? "bg-primary/10" : "hover:bg-hover/50"}`}>
                    <div className="relative h-11 w-16 shrink-0 rounded-md overflow-hidden bg-black/40 flex items-center justify-center">
                      {c.snapshot_url ? <img src={fileUrl(c.snapshot_url)} alt="" className="h-full w-full object-cover" />
                        : <Icon icon="heroicons-outline:video-camera-slash" className="text-muted" />}
                      <span className={`absolute bottom-0.5 left-0.5 h-1.5 w-1.5 rounded-full ${c.status === "online" ? "bg-green-500" : c.status === "error" ? "bg-red-500" : "bg-slate-500"}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm truncate ${sel ? "font-semibold text-foreground" : "text-foreground"}`}>{c.name}</div>
                      <div className="text-xs text-muted truncate">{c.location || c.zone || "—"}</div>
                    </div>
                    {c.recognition_enabled
                      ? <Icon icon="heroicons-solid:sparkles" className="text-green-500 text-sm shrink-0" title="Recognition on" />
                      : <span className="text-[10px] text-muted shrink-0">off</span>}
                  </button>
                );
              })}
            </div>
          </div>

          {/* RIGHT 80% — selected camera config */}
          <div className="lg:h-full min-h-0">
            {selected ? (
              <CameraConfigPanel key={selected.id} camera={selected} qc={qc} onDeleted={() => setSelectedId(null)} />
            ) : (
              <div className="rounded-xl border border-dashed border-card-border lg:h-full flex flex-col items-center justify-center p-16 text-center text-sm text-muted">
                <Icon icon="heroicons-outline:cog-6-tooth" className="text-3xl mx-auto mb-2 opacity-60" />
                Select a camera to configure its parameters and ROI.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Simple onboarding — just the essentials; params + ROI live in the detail pane. */}
      <Modal open={openCreate} onClose={() => setOpenCreate(false)} title="Add camera"
        footer={<><Button variant="secondary" onClick={() => setOpenCreate(false)}>Cancel</Button><Button variant="success" disabled={!createValid || create.isPending} onClick={() => create.mutate({ name: createForm.name.trim(), rtsp_url: createForm.rtsp_url.trim(), location: createForm.location || null })}>{create.isPending ? "Adding…" : "Add camera"}</Button></>}>
        <div className="space-y-4">
          <Input label="Name" value={createForm.name} onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} placeholder="e.g. Lobby entrance" autoFocus />
          <Input label="RTSP URL" value={createForm.rtsp_url} onChange={(e) => setCreateForm({ ...createForm, rtsp_url: e.target.value })} placeholder="rtsp://user:pass@host:554/stream" />
          <Input label="Location" value={createForm.location} onChange={(e) => setCreateForm({ ...createForm, location: e.target.value })} placeholder="Main lobby" />
          <p className="text-xs text-muted">The camera is added with recognition <strong>off</strong>. Configure parameters + ROI in the detail pane, then turn recognition on.</p>
        </div>
      </Modal>
    </div>
  );
}
