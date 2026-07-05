"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, ConfirmDialog, EmptyState, Input, Modal, Select, Spinner, Toggle } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

import { CAM_DIRECTIONS, CAM_HWACCEL, CAM_STATUS_COLOR, fmt } from "./shared";

const EMPTY = {
  name: "", rtsp_url: "", location: "", zone: "", direction: "both", hw_accel: "none",
  recognition_enabled: true, enabled: true, min_confidence: 0.5, fps: 5, min_face_px: 40,
};

export default function CamerasTab() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [confirm, setConfirm] = useState(null);

  const cams = useQuery({ queryKey: ["frs-cameras"], queryFn: () => api.get("/frs/cameras").then((r) => r.data) });

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["frs-cameras"] }); setOpen(false); setEditing(null); setForm(EMPTY); };
  const create = useMutation({ mutationFn: (b) => api.post("/frs/cameras", b), onSuccess: () => { toast.success("Camera added"); invalidate(); }, onError: (e) => toast.error(apiError(e)) });
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.put(`/frs/cameras/${id}`, b), onSuccess: () => { toast.success("Camera updated"); invalidate(); }, onError: (e) => toast.error(apiError(e)) });
  const remove = useMutation({ mutationFn: (id) => api.delete(`/frs/cameras/${id}`), onSuccess: () => { toast.success("Camera deleted"); qc.invalidateQueries({ queryKey: ["frs-cameras"] }); setConfirm(null); }, onError: (e) => toast.error(apiError(e)) });
  const test = useMutation({
    mutationFn: (id) => api.post(`/frs/cameras/${id}/test`),
    onSuccess: (r) => { r.data.status === "online" ? toast.success("Camera reachable") : toast.error(r.data.last_error || "Camera unreachable"); qc.invalidateQueries({ queryKey: ["frs-cameras"] }); },
    onError: (e) => toast.error(apiError(e)),
  });

  function openCreate() { setEditing(null); setForm(EMPTY); setOpen(true); }
  function openEdit(c) {
    setEditing(c);
    setForm({
      name: c.name || "", rtsp_url: c.rtsp_url || "", location: c.location || "", zone: c.zone || "",
      direction: c.direction || "both", hw_accel: c.hw_accel || "none",
      recognition_enabled: !!c.recognition_enabled, enabled: !!c.enabled,
      min_confidence: c.min_confidence ?? 0.5, fps: c.fps ?? 5, min_face_px: c.min_face_px ?? 40,
    });
    setOpen(true);
  }
  function save() {
    const b = {
      name: form.name, rtsp_url: form.rtsp_url, location: form.location || null, zone: form.zone || null,
      direction: form.direction, hw_accel: form.hw_accel, recognition_enabled: form.recognition_enabled,
      enabled: form.enabled, min_confidence: Number(form.min_confidence), fps: Number(form.fps),
      min_face_px: Number(form.min_face_px),
    };
    editing ? patch.mutate({ id: editing.id, ...b }) : create.mutate(b);
  }
  const saving = create.isPending || patch.isPending;
  const list = cams.data || [];
  const online = list.filter((c) => c.status === "online").length;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-muted">Cameras · {list.length}{list.length > 0 && <> · <span className="text-green-500">{online} online</span></>}</div>
        <Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>Add camera</Button>
      </div>

      {cams.isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : list.length === 0 ? (
        <EmptyState icon="heroicons-outline:video-camera" title="No cameras yet" subtitle="Add an RTSP video source to start face recognition." action={<Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>Add camera</Button>} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {list.map((c) => (
            <div key={c.id} className="group rounded-xl border border-card-border bg-card overflow-hidden">
              <div className="relative aspect-video bg-black/40 flex items-center justify-center">
                {c.snapshot_url ? (
                  <img src={fileUrl(c.snapshot_url)} alt={c.name} className="h-full w-full object-cover" />
                ) : (
                  <Icon icon="heroicons-outline:video-camera-slash" className="text-3xl text-muted" />
                )}
                <div className="absolute top-2 left-2"><Badge color={CAM_STATUS_COLOR[c.status] || "slate"}>{c.status}</Badge></div>
                {!c.recognition_enabled && <div className="absolute top-2 right-2"><Badge color="slate">FRS off</Badge></div>}
              </div>
              <div className="p-3.5">
                <div className="flex items-start justify-between">
                  <div className="min-w-0">
                    <div className="font-medium text-foreground truncate">{c.name}</div>
                    <div className="text-xs text-muted truncate flex items-center gap-1"><Icon icon="heroicons-outline:map-pin" />{c.location || c.zone || "—"}</div>
                  </div>
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition shrink-0">
                    <button title="Test connection" disabled={test.isPending} onClick={() => test.mutate(c.id)} className="p-1.5 text-muted hover:text-foreground"><Icon icon="heroicons-outline:signal" /></button>
                    <button title="Edit" onClick={() => openEdit(c)} className="p-1.5 text-muted hover:text-foreground"><Icon icon="heroicons-outline:pencil-square" /></button>
                    <button title="Delete" onClick={() => setConfirm({ title: "Delete camera", message: <>Delete <strong>{c.name}</strong>?</>, confirmLabel: "Delete camera", onConfirm: () => remove.mutate(c.id) })} className="p-1.5 text-red-500 hover:text-red-400"><Icon icon="heroicons-outline:trash" /></button>
                  </div>
                </div>
                <div className="flex items-center justify-between mt-3 pt-3 border-t border-card-border text-xs text-muted">
                  <span className="flex items-center gap-1 capitalize"><Icon icon="heroicons-outline:arrows-right-left" />{c.direction}</span>
                  <span className="flex items-center gap-1"><Icon icon="heroicons-outline:bolt" />{c.events_24h} / 24h</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? "Edit camera" : "Add camera"}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button variant={editing ? "primary" : "success"} disabled={saving || !form.name || !form.rtsp_url} onClick={save}>{saving ? "Saving…" : editing ? "Save" : "Add"}</Button></>}>
        <div className="space-y-4">
          <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Lobby entrance" autoFocus />
          <Input label="RTSP URL" value={form.rtsp_url} onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })} placeholder="rtsp://user:pass@host:554/stream" />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Main lobby" />
            <Input label="Zone" value={form.zone} onChange={(e) => setForm({ ...form, zone: e.target.value })} placeholder="Ground floor" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Select label="Direction" options={CAM_DIRECTIONS} value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })} />
            <Select label="Decode" options={CAM_HWACCEL} value={form.hw_accel} onChange={(e) => setForm({ ...form, hw_accel: e.target.value })} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Input label="Min confidence" type="number" step="0.05" min="0" max="1" value={form.min_confidence} onChange={(e) => setForm({ ...form, min_confidence: e.target.value })} />
            <Input label="Process FPS" type="number" min="1" max="30" value={form.fps} onChange={(e) => setForm({ ...form, fps: e.target.value })} />
            <Input label="Min face px" type="number" min="10" value={form.min_face_px} onChange={(e) => setForm({ ...form, min_face_px: e.target.value })} />
          </div>
          <div className="flex items-center justify-between rounded-md border border-card-border px-3 py-2.5">
            <div><span className="text-sm font-medium text-foreground">Run recognition</span><div className="text-xs text-muted">Process this camera in the live pipeline.</div></div>
            <Toggle checked={form.recognition_enabled} onChange={(v) => setForm({ ...form, recognition_enabled: v })} />
          </div>
          <div className="flex items-center justify-between rounded-md border border-card-border px-3 py-2.5">
            <div><span className="text-sm font-medium text-foreground">Enabled</span><div className="text-xs text-muted">Disable to stop streaming without deleting.</div></div>
            <Toggle checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} />
          </div>
        </div>
      </Modal>

      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={remove.isPending} />
    </div>
  );
}
