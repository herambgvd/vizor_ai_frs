"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, Modal, PageHeader, Spinner, Table } from "@/web/kit";
import { api, apiError } from "@/web/api";

const EMPTY = { name: "", description: "", permissions: [] };

export default function RolesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null); // the role being edited, or null when creating
  const [form, setForm] = useState(EMPTY);
  const [confirm, setConfirm] = useState(null);

  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => api.get("/auth/roles", { params: { page_size: 100 } }).then((r) => r.data),
  });
  const catalog = useQuery({
    queryKey: ["permissions"],
    queryFn: () => api.get("/auth/permissions").then((r) => r.data),
  });
  const groups = catalog.data?.groups || {};

  const readOnly = !!editing?.is_system;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["roles"] });
    setOpen(false);
    setEditing(null);
    setForm(EMPTY);
  };

  const create = useMutation({
    mutationFn: (body) => api.post("/auth/roles", body),
    onSuccess: () => {
      toast.success("Role created");
      invalidate();
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const patch = useMutation({
    mutationFn: ({ id, ...body }) => api.patch(`/auth/roles/${id}`, body),
    onSuccess: () => {
      toast.success("Role updated");
      invalidate();
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const remove = useMutation({
    mutationFn: (id) => api.delete(`/auth/roles/${id}`),
    onSuccess: () => {
      toast.success("Role deleted");
      qc.invalidateQueries({ queryKey: ["roles"] });
      setConfirm(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  function openCreate() {
    setEditing(null);
    setForm(EMPTY);
    setOpen(true);
  }
  function openEdit(role) {
    setEditing(role);
    setForm({
      name: role.name || "",
      description: role.description || "",
      permissions: [...(role.permissions || [])],
    });
    setOpen(true);
  }
  function handleDelete(role) {
    setConfirm({
      title: "Delete role",
      message: <>Delete role <strong>{role.name}</strong>? This can’t be undone.</>,
      confirmLabel: "Delete role",
      onConfirm: () => remove.mutate(role.id),
    });
  }

  const selected = useMemo(() => new Set(form.permissions), [form.permissions]);
  const allKeys = useMemo(
    () => Object.values(groups).flatMap((perms) => perms.map((p) => p.key)),
    [groups]
  );

  function toggleKey(key) {
    if (readOnly) return;
    setForm((f) => {
      const next = new Set(f.permissions);
      next.has(key) ? next.delete(key) : next.add(key);
      return { ...f, permissions: [...next] };
    });
  }
  function toggleGroup(perms, checkAll) {
    if (readOnly) return;
    setForm((f) => {
      const next = new Set(f.permissions);
      perms.forEach((p) => (checkAll ? next.add(p.key) : next.delete(p.key)));
      return { ...f, permissions: [...next] };
    });
  }

  function save() {
    const body = { name: form.name, description: form.description, permissions: form.permissions };
    if (editing) patch.mutate({ id: editing.id, ...body });
    else create.mutate(body);
  }

  const permLabel = (role) => {
    const perms = role.permissions || [];
    if (perms.includes("*")) return "All permissions";
    return `${perms.length} permission${perms.length === 1 ? "" : "s"}`;
  };

  const saving = create.isPending || patch.isPending;

  const columns = [
    {
      key: "name",
      label: "Role",
      render: (role) => (
        <div>
          <div className="font-medium">{role.name}</div>
          {role.description && <div className="text-xs text-muted line-clamp-1">{role.description}</div>}
        </div>
      ),
    },
    {
      key: "perms",
      label: "Permissions",
      render: (role) => <span className="text-muted">{permLabel(role)}</span>,
    },
    {
      key: "type",
      label: "Type",
      render: (role) => (
        <Badge color={role.is_system ? "indigo" : "slate"}>{role.is_system ? "System" : "Custom"}</Badge>
      ),
    },
    {
      key: "actions",
      label: "",
      render: (role) => (
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" icon="heroicons-outline:pencil-square" onClick={() => openEdit(role)}>
            {role.is_system ? "View" : "Edit"}
          </Button>
          {!role.is_system && (
            <Button variant="danger" icon="heroicons-outline:trash" onClick={() => handleDelete(role)}>
              Delete
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Roles & Permissions"
        subtitle="Define roles and the exact permissions each one grants."
        actions={<Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>Create role</Button>}
      />

      <Card className="p-2">
        {roles.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : (
          <Table
            columns={columns}
            rows={roles.data?.items}
            empty={
              <EmptyState
                icon="heroicons-outline:shield-check"
                title="No roles yet"
                subtitle="Create your first role to start assigning permissions."
                action={<Button variant="success" icon="heroicons-outline:plus" onClick={openCreate}>Create role</Button>}
              />
            }
          />
        )}
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        wide
        title={editing ? (readOnly ? `${editing.name} (system role)` : `Edit role`) : "Create role"}
        footer={
          readOnly ? (
            <Button variant="secondary" onClick={() => setOpen(false)}>Close</Button>
          ) : (
            <>
              <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
              <Button variant={editing ? "primary" : "success"} disabled={saving || !form.name} onClick={save}>
                {saving ? "Saving…" : editing ? "Save changes" : "Create"}
              </Button>
            </>
          )
        }
      >
        <div className="space-y-5">
          {readOnly && (
            <div className="flex items-center gap-2 rounded-lg bg-blue-500/10 bg-blue-500/10 px-3 py-2 text-sm text-blue-400 text-blue-400">
              <Icon icon="heroicons-outline:lock-closed" className="text-base" />
              System roles are built in and cannot be edited.
            </div>
          )}

          <Input
            label="Name"
            value={form.name}
            disabled={readOnly}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Operator"
          />
          <Input
            label="Description"
            value={form.description}
            disabled={readOnly}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="What this role is for"
          />

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-muted text-muted">Permissions</span>
              <span className="text-xs text-muted">{form.permissions.length} selected</span>
            </div>

            {catalog.isLoading ? (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            ) : !Object.keys(groups).length ? (
              <EmptyState title="No permissions available" />
            ) : (
              <div className="space-y-4">
                {Object.entries(groups).map(([category, perms]) => {
                  const total = perms.length;
                  const chosen = perms.filter((p) => selected.has(p.key)).length;
                  const allOn = total > 0 && chosen === total;
                  return (
                    <div
                      key={category}
                      className="rounded-xl border border-card-border border-card-border overflow-hidden"
                    >
                      <div className="flex items-center justify-between bg-hover bg-hover px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-foreground text-foreground">
                            {category}
                          </span>
                          <span className="text-xs text-muted">
                            {chosen}/{total}
                          </span>
                        </div>
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => toggleGroup(perms, !allOn)}
                            className="text-xs font-medium text-blue-400 text-blue-400 hover:underline"
                          >
                            {allOn ? "Uncheck all" : "Check all"}
                          </button>
                        )}
                      </div>
                      <div className="divide-y divide-card-border">
                        {perms.map((p) => {
                          const on = selected.has(p.key);
                          return (
                            <label
                              key={p.key}
                              className={`flex items-start gap-3 px-4 py-2.5 ${
                                readOnly ? "cursor-default" : "cursor-pointer hover:bg-hover"
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={on}
                                disabled={readOnly}
                                onChange={() => toggleKey(p.key)}
                                className="mt-0.5 h-4 w-4 rounded border-card-border text-blue-400 focus:ring-card-border border-card-border bg-hover"
                              />
                              <div className="min-w-0">
                                <div className="text-sm text-foreground text-foreground">{p.label}</div>
                                {p.description && (
                                  <div className="text-xs text-muted mt-0.5">{p.description}</div>
                                )}
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </Modal>

      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={remove.isPending} />
    </div>
  );
}
