"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, ConfirmDialog, Drawer, EmptyState, Input, Modal, Select, Spinner, Toggle } from "@/web/kit";
import { api, apiError, fileUrl } from "@/web/api";

import { CATEGORIES, CATEGORY_COLOR, ENROLL_COLOR } from "./shared";

const PAGE = 24;
const DOT = { green: "bg-green-500", amber: "bg-amber-500", red: "bg-red-500", slate: "bg-slate-500", indigo: "bg-indigo-500", blue: "bg-blue-500" };
const EMPTY = {
  full_name: "", external_id: "", group_id: "", category: "standard", priority: 0,
  department: "", designation: "", contact_number: "", date_of_joining: "",
  id_type: "", id_number: "", validity_start: "", validity_end: "", auto_remove: false,
};
function clean(f) {
  const o = {};
  for (const [k, v] of Object.entries(f)) o[k] = k === "priority" ? Number(v) || 0 : k === "auto_remove" ? !!v : v === "" ? null : v;
  return o;
}

export default function PersonsTab() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [selected, setSelected] = useState(null); // person open in drawer
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [confirm, setConfirm] = useState(null);
  const [importOpen, setImportOpen] = useState(false);

  const groups = useQuery({ queryKey: ["frs-groups"], queryFn: () => api.get("/frs/groups").then((r) => r.data) });
  const groupOpts = (groups.data || []).map((g) => ({ value: g.id, label: g.name }));
  const groupName = (id) => (groups.data || []).find((g) => g.id === id)?.name || "No group";

  const persons = useQuery({
    queryKey: ["frs-persons", page, search, groupFilter],
    queryFn: () => api.get("/frs/persons", { params: { page, page_size: PAGE, search: search || undefined, group_id: groupFilter || undefined } }).then((r) => r.data),
    keepPreviousData: true,
  });

  const invalidate = () => { qc.invalidateQueries({ queryKey: ["frs-persons"] }); qc.invalidateQueries({ queryKey: ["frs-groups"] }); };
  const create = useMutation({ mutationFn: (b) => api.post("/frs/persons", b), onSuccess: () => { toast.success("Person added"); invalidate(); setFormOpen(false); }, onError: (e) => toast.error(apiError(e)) });
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.put(`/frs/persons/${id}`, b), onSuccess: (r) => { toast.success("Person updated"); invalidate(); setFormOpen(false); if (selected) setSelected(r.data); }, onError: (e) => toast.error(apiError(e)) });
  const remove = useMutation({ mutationFn: (id) => api.delete(`/frs/persons/${id}`), onSuccess: () => { toast.success("Person deleted"); invalidate(); setConfirm(null); setSelected(null); }, onError: (e) => toast.error(apiError(e)) });

  function openCreate() { setEditing(null); setForm(EMPTY); setFormOpen(true); }
  function openEdit(p) {
    setEditing(p);
    setForm({ full_name: p.full_name || "", external_id: p.external_id || "", group_id: p.group_id || "", category: p.category || "standard", priority: p.priority || 0, department: p.department || "", designation: p.designation || "", contact_number: p.contact_number || "", date_of_joining: p.date_of_joining || "", id_type: p.id_type || "", id_number: p.id_number || "", validity_start: p.validity_start || "", validity_end: p.validity_end || "", auto_remove: !!p.auto_remove });
    setFormOpen(true);
  }
  const saving = create.isPending || patch.isPending;
  const data = persons.data;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="text-sm text-muted mr-auto">Persons · {data?.total ?? 0}</div>
        <div className="w-56"><Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search name or ID…" /></div>
        <div className="w-44"><Select options={[{ value: "", label: "All groups" }, ...groupOpts]} value={groupFilter} onChange={(e) => { setGroupFilter(e.target.value); setPage(1); }} placeholder="All groups" /></div>
        <Button variant="secondary" icon="heroicons-outline:arrow-up-tray" onClick={() => setImportOpen(true)}>Import</Button>
        <Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>Add person</Button>
      </div>

      {persons.isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : !data?.items?.length ? (
        <EmptyState icon="heroicons-outline:user-group" title="No persons yet" subtitle="Add a person or bulk-import a spreadsheet." action={<Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>Add person</Button>} />
      ) : (
        <>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
            {data.items.map((p) => (
              <button key={p.id} onClick={() => setSelected(p)} className="group text-left rounded-lg border border-card-border bg-card overflow-hidden hover:border-muted transition">
                <div className="relative aspect-square bg-hover/40 overflow-hidden">
                  {p.thumbnail_key ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={fileUrl(p.thumbnail_key)} alt={p.full_name} className="h-full w-full object-cover" />
                  ) : (
                    <div className="h-full flex items-center justify-center text-muted"><Icon icon="heroicons-outline:user" className="text-3xl" /></div>
                  )}
                  <span className={`absolute top-1.5 left-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-card ${DOT[ENROLL_COLOR[p.enrollment_status]] || DOT.slate}`} title={p.enrollment_status} />
                  {p.category && p.category !== "standard" && <span className={`absolute top-1.5 right-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-card ${DOT[CATEGORY_COLOR[p.category]] || DOT.slate}`} title={p.category} />}
                </div>
                <div className="p-2">
                  <div className="text-sm font-medium text-foreground truncate">{p.full_name}</div>
                  <div className="text-xs text-muted truncate">{groupName(p.group_id)}</div>
                </div>
              </button>
            ))}
          </div>
          {data.pages > 1 && (
            <div className="flex items-center justify-end gap-2 mt-4 text-sm text-muted">
              <Button variant="secondary" disabled={!data.has_prev} onClick={() => setPage((p) => p - 1)}>Prev</Button>
              <span>Page {data.page} / {data.pages}</span>
              <Button variant="secondary" disabled={!data.has_next} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          )}
        </>
      )}

      <PersonDrawer person={selected} onClose={() => setSelected(null)} groupName={groupName} onEdit={openEdit} onDelete={(p) => setConfirm({ title: "Delete person", message: <>Delete <strong>{p.full_name}</strong>? All data (profile, ID, photos) is erased.</>, confirmLabel: "Delete person", onConfirm: () => remove.mutate(p.id) })} />

      <Modal open={formOpen} onClose={() => setFormOpen(false)} wide title={editing ? "Edit person" : "Add person"}
        footer={<><Button variant="secondary" onClick={() => setFormOpen(false)}>Cancel</Button><Button variant={editing ? "primary" : "success"} disabled={saving || !form.full_name} onClick={() => { const b = clean(form); editing ? patch.mutate({ id: editing.id, ...b }) : create.mutate(b); }}>{saving ? "Saving…" : editing ? "Save changes" : "Add person"}</Button></>}>
        <PersonForm form={form} setForm={setForm} groupOpts={groupOpts} />
      </Modal>

      <ImportModal open={importOpen} onClose={() => setImportOpen(false)} onDone={invalidate} />
      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={remove.isPending} />
    </div>
  );
}

// --- person detail drawer ----------------------------------------------------
function PersonDrawer({ person, onClose, groupName, onEdit, onDelete }) {
  const qc = useQueryClient();
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const photos = useQuery({ queryKey: ["frs-photos", person?.id], queryFn: () => api.get(`/frs/persons/${person.id}/photos`).then((r) => r.data), enabled: !!person });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["frs-photos", person.id] }); qc.invalidateQueries({ queryKey: ["frs-persons"] }); };

  async function onUpload(e) {
    const f = e.target.files?.[0]; e.target.value = ""; if (!f) return;
    setBusy(true);
    try { const fd = new FormData(); fd.append("file", f); const { data } = await api.post(`/frs/persons/${person.id}/photos`, fd); data.status === "enrolled" ? toast.success("Photo enrolled") : toast.error(`Not enrolled: ${data.error || data.status}`); refresh(); }
    catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  }
  const del = (id) => api.delete(`/frs/photos/${id}`).then(refresh).catch((e) => toast.error(apiError(e)));
  const retry = (id) => api.post(`/frs/photos/${id}/retry`).then(() => { toast.success("Re-enrolled"); refresh(); }).catch((e) => toast.error(apiError(e)));
  async function viewId() { try { const { data } = await api.get(`/frs/persons/${person.id}/id-document`); window.open(fileUrl(data.url), "_blank"); } catch (e) { toast.error(apiError(e)); } }

  if (!person) return null;
  const items = photos.data || [];
  const Meta = ({ label, value }) => value ? <div><div className="text-[11px] uppercase tracking-wide text-muted">{label}</div><div className="text-sm text-foreground">{value}</div></div> : null;

  return (
    <Drawer open={!!person} onClose={onClose} title={person.full_name} subtitle={person.external_id ? `ID · ${person.external_id}` : null}>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Badge color={ENROLL_COLOR[person.enrollment_status] || "slate"}>{person.enrollment_status}</Badge>
        <Badge color="slate">{groupName(person.group_id)}</Badge>
        <Badge color="indigo">P{person.priority}</Badge>
        {person.photo_count > 0 && <span className="text-xs text-muted">{person.enrolled_photo_count}/{person.photo_count} enrolled</span>}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <Meta label="Department" value={person.department} />
        <Meta label="Designation" value={person.designation} />
        <Meta label="Contact" value={person.contact_number} />
        <Meta label="Category" value={person.category} />
        <Meta label="ID" value={person.id_type ? `${person.id_type}: ${person.id_number || "—"}` : null} />
        <Meta label="Validity" value={person.validity_end ? `till ${person.validity_end}${person.auto_remove ? " · auto-remove" : ""}` : null} />
      </div>
      {person.has_id_document && <Button variant="secondary" icon="heroicons-outline:document" onClick={viewId} className="mb-4">View ID document</Button>}

      <div className="flex items-center gap-2 mb-4 pb-4 border-b border-card-border">
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onUpload} />
        <Button variant="primary" icon="heroicons-outline:camera" disabled={busy} onClick={() => fileRef.current?.click()}>{busy ? "Enrolling…" : "Upload photo"}</Button>
        <Button variant="secondary" icon="heroicons-outline:pencil-square" onClick={() => onEdit(person)}>Edit</Button>
        <Button variant="ghost" icon="heroicons-outline:trash" className="text-red-500 ml-auto" onClick={() => onDelete(person)} />
      </div>

      <div className="text-sm font-medium text-foreground mb-2">Face photos</div>
      {photos.isLoading ? <div className="flex justify-center py-6"><Spinner /></div> : items.length === 0 ? (
        <div className="text-center text-muted text-xs py-6 border border-dashed border-card-border rounded-lg"><Icon icon="heroicons-outline:photo" className="text-2xl mx-auto mb-1" />No photos — upload to enroll</div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {items.map((ph) => (
            <div key={ph.id} className="rounded-lg border border-card-border overflow-hidden bg-hover/30">
              <div className="relative aspect-square bg-black/20 overflow-hidden">
                {ph.image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={fileUrl(ph.image_url)} alt="face" className="h-full w-full object-cover" />
                )}
                <div className="absolute top-1 right-1 flex gap-0.5">
                  {ph.status === "failed" && <button onClick={() => retry(ph.id)} title="Retry" className="p-1 rounded bg-black/50 text-white"><Icon icon="heroicons-outline:arrow-path" className="text-xs" /></button>}
                  <button onClick={() => del(ph.id)} title="Delete" className="p-1 rounded bg-black/50 text-red-400"><Icon icon="heroicons-outline:trash" className="text-xs" /></button>
                </div>
                <span className={`absolute bottom-1 left-1 text-[10px] px-1 rounded ${ENROLL_COLOR[ph.status] === "green" ? "bg-green-500/80" : ENROLL_COLOR[ph.status] === "red" ? "bg-red-500/80" : "bg-amber-500/80"} text-white`}>{ph.status}</span>
              </div>
              <div className="p-1 text-[10px] text-muted">
                {ph.quality_score != null && <div>Q {ph.quality_score}</div>}
                {ph.status === "failed" && ph.error && <div className="text-red-500 line-clamp-2" title={ph.error}>{ph.error}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}

// --- person create/edit form -------------------------------------------------
function PersonForm({ form, setForm, groupOpts }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Input label="Full name" value={form.full_name} onChange={set("full_name")} placeholder="e.g. Ravi Kumar" autoFocus />
      <Input label="External ID" value={form.external_id} onChange={set("external_id")} placeholder="HR id, badge no…" />
      <Select label="Group" options={[{ value: "", label: "— none —" }, ...groupOpts]} value={form.group_id} onChange={(e) => setForm({ ...form, group_id: e.target.value })} />
      <Select label="Category" options={CATEGORIES} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
      <Input label="Department" value={form.department} onChange={set("department")} />
      <Input label="Designation" value={form.designation} onChange={set("designation")} />
      <Input label="Contact number" value={form.contact_number} onChange={set("contact_number")} placeholder="+91…" />
      <Input label="Priority" type="number" value={form.priority} onChange={set("priority")} />
      <Input label="ID type" value={form.id_type} onChange={set("id_type")} placeholder="Aadhaar, PAN…" />
      <Input label="ID number" value={form.id_number} onChange={set("id_number")} />
      <Input label="Date of joining" type="date" value={form.date_of_joining || ""} onChange={set("date_of_joining")} />
      <div />
      <Input label="Validity start" type="date" value={form.validity_start || ""} onChange={set("validity_start")} />
      <Input label="Validity end" type="date" value={form.validity_end || ""} onChange={set("validity_end")} hint="Max 6-month window" />
      <div className="sm:col-span-2 flex items-center justify-between rounded-md border border-card-border px-3 py-2.5">
        <div><div className="text-sm font-medium text-foreground">Auto-remove after validity</div><div className="text-xs text-muted">Purge this person when the validity window ends.</div></div>
        <Toggle checked={form.auto_remove} onChange={(v) => setForm({ ...form, auto_remove: v })} />
      </div>
    </div>
  );
}

// --- bulk import -------------------------------------------------------------
function ImportModal({ open, onClose, onDone }) {
  const ref = useRef(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  async function onFile(e) {
    const f = e.target.files?.[0]; e.target.value = ""; if (!f) return;
    setBusy(true);
    try { const fd = new FormData(); fd.append("file", f); const { data } = await api.post("/frs/persons/import", fd); setResult(data); onDone(); toast.success(`${data.created} created, ${data.updated} updated`); }
    catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  }
  function template() { api.get("/frs/persons/import-template", { responseType: "blob" }).then((r) => { const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = "persons-import-template.xlsx"; a.click(); URL.revokeObjectURL(u); }); }
  return (
    <Modal open={open} onClose={onClose} title="Bulk import persons" footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      <div className="space-y-4">
        <p className="text-sm text-muted">Upload an XLSX/CSV. Match by <code>external_id</code> to update; resolve <code>group</code> by name.</p>
        <div className="flex items-center gap-2">
          <Button variant="secondary" icon="heroicons-outline:arrow-down-tray" onClick={template}>Download template</Button>
          <input ref={ref} type="file" accept=".xlsx,.csv" className="hidden" onChange={onFile} />
          <Button variant="primary" icon="heroicons-outline:arrow-up-tray" disabled={busy} onClick={() => ref.current?.click()}>{busy ? "Importing…" : "Choose file"}</Button>
        </div>
        {result && (
          <div className="rounded-md border border-card-border bg-hover/40 p-3 text-sm space-y-1">
            <div className="flex gap-4"><span className="text-green-500">{result.created} created</span><span className="text-blue-400">{result.updated} updated</span><span className="text-muted">{result.skipped} skipped</span></div>
            {result.errors?.length > 0 && <ul className="text-xs text-red-500 mt-1 list-disc pl-4">{result.errors.map((er, i) => <li key={i}>Row {er.row}: {er.error}</li>)}</ul>}
          </div>
        )}
      </div>
    </Modal>
  );
}
