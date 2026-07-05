"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useState } from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, EmptyState, Input, Modal, Select, Spinner, Textarea, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";

import { GROUP_TYPES, SWATCHES } from "./shared";

const EMPTY = { name: "", group_type: "employee", color_code: "#3b82f6", description: "", alert_sound: "" };

export default function GroupsTab() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [confirm, setConfirm] = useState(null);

  const groups = useQuery({ queryKey: ["frs-groups"], queryFn: () => api.get("/frs/groups").then((r) => r.data) });

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["frs-groups"] }); setOpen(false); setEditing(null); setForm(EMPTY); };
  const create = useMutation({ mutationFn: (b) => api.post("/frs/groups", b), onSuccess: () => { toast.success("Group created"); invalidate(); }, onError: (e) => toast.error(apiError(e)) });
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.put(`/frs/groups/${id}`, b), onSuccess: () => { toast.success("Group updated"); invalidate(); }, onError: (e) => toast.error(apiError(e)) });
  const remove = useMutation({ mutationFn: (id) => api.delete(`/frs/groups/${id}`), onSuccess: () => { toast.success("Group deleted"); qc.invalidateQueries({ queryKey: ["frs-groups"] }); setConfirm(null); }, onError: (e) => toast.error(apiError(e)) });

  function openCreate() { setEditing(null); setForm(EMPTY); setOpen(true); }
  function openEdit(g) { setEditing(g); setForm({ name: g.name || "", group_type: g.group_type || "employee", color_code: g.color_code || "#3b82f6", description: g.description || "", alert_sound: g.alert_sound || "" }); setOpen(true); }
  function save() {
    const b = { name: form.name, group_type: form.group_type, color_code: form.color_code, description: form.description || null, alert_sound: form.alert_sound || null };
    editing ? patch.mutate({ id: editing.id, ...b }) : create.mutate(b);
  }
  const saving = create.isPending || patch.isPending;
  const list = groups.data || [];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-muted">Groups · {list.length}</div>
        <Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>New group</Button>
      </div>

      {groups.isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : list.length === 0 ? (
        <EmptyState icon="heroicons-outline:user-group" title="No groups yet" subtitle="Create a watchlist to start grouping persons." action={<Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>New group</Button>} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {list.map((g) => (
            <div key={g.id} className="group rounded-xl border border-card-border bg-card overflow-hidden">
              <div className="h-1.5" style={{ backgroundColor: g.color_code }} />
              <div className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: `${g.color_code}22`, color: g.color_code }}>
                      <Icon icon="heroicons-outline:folder" className="text-lg" />
                    </div>
                    <div className="min-w-0">
                      <div className="font-medium text-foreground truncate">{g.name}</div>
                      <div className="text-xs text-muted capitalize">{g.group_type}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition">
                    <button title="Edit" onClick={() => openEdit(g)} className="p-1.5 text-muted hover:text-foreground"><Icon icon="heroicons-outline:pencil-square" /></button>
                    <button title="Delete" onClick={() => setConfirm({ title: "Delete group", message: <>Delete <strong>{g.name}</strong>? Its persons are kept but un-grouped.</>, confirmLabel: "Delete group", onConfirm: () => remove.mutate(g.id) })} className="p-1.5 text-red-500 hover:text-red-400"><Icon icon="heroicons-outline:trash" /></button>
                  </div>
                </div>
                {g.description && <p className="text-xs text-muted mt-3 line-clamp-2">{g.description}</p>}
                <div className="flex items-center justify-between mt-4 pt-3 border-t border-card-border text-xs">
                  <span className="flex items-center gap-1.5 text-muted"><Icon icon="heroicons-outline:users" /> <span className="font-medium text-foreground">{g.person_count}</span> members</span>
                  <span className={`flex items-center gap-1 ${g.alert_sound ? "text-amber-500" : "text-muted"}`}>
                    <Icon icon={g.alert_sound ? "heroicons-solid:bell-alert" : "heroicons-outline:bell-slash"} /> {g.alert_sound ? "Alert" : "Silent"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? "Edit group" : "New group"}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button variant={editing ? "primary" : "success"} disabled={saving || !form.name} onClick={save}>{saving ? "Saving…" : editing ? "Save" : "Create"}</Button></>}>
        <div className="space-y-4">
          <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. VIP guests" autoFocus />
          <Select label="Type" options={GROUP_TYPES} value={form.group_type} onChange={(e) => setForm({ ...form, group_type: e.target.value })} />
          <div>
            <span className="block text-sm font-medium text-foreground mb-1.5">Colour</span>
            <div className="flex items-center gap-2">
              {SWATCHES.map((c) => (
                <button key={c} onClick={() => setForm({ ...form, color_code: c })} className={`h-7 w-7 rounded-full border-2 ${form.color_code === c ? "border-foreground" : "border-transparent"}`} style={{ backgroundColor: c }} />
              ))}
              <input type="color" value={form.color_code} onChange={(e) => setForm({ ...form, color_code: e.target.value })} className="h-7 w-9 rounded border border-card-border bg-transparent cursor-pointer" />
            </div>
          </div>
          <Textarea label="Description" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <div className="flex items-center justify-between rounded-md border border-card-border px-3 py-2.5">
            <span className="text-sm font-medium text-foreground">Alert sound</span>
            <Toggle checked={!!form.alert_sound} onChange={(v) => setForm({ ...form, alert_sound: v ? "default" : "" })} />
          </div>
        </div>
      </Modal>

      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={remove.isPending} />
    </div>
  );
}
