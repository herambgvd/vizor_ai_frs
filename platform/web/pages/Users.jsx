"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Avatar, Badge, Button, Card, Input, Modal, PageHeader, Select, Spinner, Table, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";
import { useAuth } from "@/web/auth";

// "Never", or a compact relative/absolute last-login time.
function fmtLogin(ts) {
  if (!ts) return "Never";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMin = (Date.now() - d.getTime()) / 60000;
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${Math.floor(diffMin)}m ago`;
  if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function UsersPage() {
  const qc = useQueryClient();
  const { can, user: me } = useAuth();
  const canManage = can("user.manage");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", full_name: "", role_id: "", send_invite: true });
  const [editing, setEditing] = useState(null); // user being edited, or null
  const [editForm, setEditForm] = useState({ full_name: "", role_id: "", is_active: true });
  const [deleting, setDeleting] = useState(null); // user being deleted, or null
  const [delPassword, setDelPassword] = useState("");
  const importRef = useRef(null);

  async function exportUsers() {
    try {
      const res = await api.get("/auth/users/export", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "users.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(apiError(e));
    }
  }

  const importUsers = useMutation({
    mutationFn: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post("/auth/users/import", fd).then((r) => r.data);
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success(`Imported ${r.created} user(s)${r.skipped ? `, ${r.skipped} skipped` : ""}`);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  function onPickImport(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) importUsers.mutate(file);
  }

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get("/auth/users", { params: { page_size: 100 } }).then((r) => r.data),
  });
  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => api.get("/auth/roles", { params: { page_size: 100 } }).then((r) => r.data),
  });
  const roleOptions = (roles.data?.items || []).map((r) => ({ value: r.id, label: r.name }));

  const create = useMutation({
    mutationFn: (body) => api.post("/auth/users", body),
    onSuccess: () => {
      toast.success("User created");
      qc.invalidateQueries({ queryKey: ["users"] });
      setOpen(false);
      setForm({ email: "", password: "", full_name: "", role_id: "", send_invite: true });
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const patch = useMutation({
    mutationFn: ({ id, ...body }) => api.patch(`/auth/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e) => toast.error(apiError(e)),
  });
  const saveEdit = useMutation({
    mutationFn: ({ id, ...body }) => api.patch(`/auth/users/${id}`, body),
    onSuccess: () => {
      toast.success("User updated");
      qc.invalidateQueries({ queryKey: ["users"] });
      setEditing(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const remove = useMutation({
    // DELETE with a confirmation body: the acting admin re-enters their password.
    mutationFn: ({ id, password }) => api.delete(`/auth/users/${id}`, { data: { password } }),
    onSuccess: () => {
      toast.success("User deleted");
      qc.invalidateQueries({ queryKey: ["users"] });
      setDeleting(null);
      setDelPassword("");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  function openEdit(u) {
    setEditForm({ full_name: u.full_name || "", role_id: u.role.id, is_active: u.is_active });
    setEditing(u);
  }

  const columns = [
    {
      key: "email",
      label: "User",
      render: (u) => (
        <div className="flex items-center gap-3">
          <Avatar src={u.avatar_url} name={u.full_name || u.email} size={32} />
          <div className="min-w-0">
            <div className="font-medium">{u.full_name || "—"}</div>
            <div className="text-xs text-muted">{u.email}</div>
          </div>
        </div>
      ),
    },
    {
      key: "role",
      label: "Role",
      render: (u) => <span className="font-medium">{u.role?.name || "—"}</span>,
    },
    {
      key: "email_verified",
      label: "Verified",
      render: (u) => (
        <Badge color={u.email_verified ? "green" : "amber"}>
          {u.email_verified ? "Verified" : "Pending"}
        </Badge>
      ),
    },
    {
      key: "last_login_at",
      label: "Last login",
      render: (u) => <span className="text-muted">{fmtLogin(u.last_login_at)}</span>,
    },
    {
      key: "is_active",
      label: "Status",
      render: (u) => (
        <Badge color={u.is_active ? "green" : "slate"}>{u.is_active ? "Active" : "Disabled"}</Badge>
      ),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            label: "",
            render: (u) => (
              <div className="flex items-center justify-end gap-1">
                <Button variant="ghost" icon="heroicons-outline:pencil-square" onClick={() => openEdit(u)}>
                  Edit
                </Button>
                {u.id !== me?.id && (
                  <Button variant="danger" icon="heroicons-outline:trash" onClick={() => setDeleting(u)}>
                    Delete
                  </Button>
                )}
              </div>
            ),
          },
        ]
      : []),
  ];

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="Manage who can access the platform and their roles."
        actions={
          <div className="flex items-center gap-2">
            <input ref={importRef} type="file" accept=".csv,text/csv" className="hidden" onChange={onPickImport} />
            <Button variant="secondary" icon="heroicons-outline:arrow-down-tray" onClick={exportUsers}>
              Export
            </Button>
            {canManage && (
              <Button
                variant="secondary"
                icon="heroicons-outline:arrow-up-tray"
                disabled={importUsers.isPending}
                onClick={() => importRef.current?.click()}
              >
                {importUsers.isPending ? "Importing…" : "Import"}
              </Button>
            )}
            {canManage && (
              <Button variant="success" icon="heroicons-outline:plus" onClick={() => setOpen(true)}>
                Add user
              </Button>
            )}
          </div>
        }
      />
      <Card className="p-2">
        {users.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : (
          <Table columns={columns} rows={users.data?.items} />
        )}
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Add user"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="success"
              disabled={create.isPending || !form.email || !form.password || !form.role_id}
              onClick={() => create.mutate(form)}
            >
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Jane Doe" />
          <Input label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="jane@example.com" />
          <Input label="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} hint="At least 8 characters, with a letter and a number." />
          <Select
            label="Role"
            value={form.role_id}
            options={[{ value: "", label: "Select a role…" }, ...roleOptions]}
            onChange={(e) => setForm({ ...form, role_id: e.target.value })}
          />
          <div className="flex items-center justify-between rounded-lg border border-card-border px-3 py-2.5">
            <div>
              <div className="text-sm font-medium text-foreground">Send invite email</div>
              <div className="text-xs text-muted">
                Emails a welcome message + a secure link to set their password.
              </div>
            </div>
            <Toggle
              checked={form.send_invite}
              onChange={(v) => setForm({ ...form, send_invite: v })}
            />
          </div>
        </div>
      </Modal>

      {/* Edit user */}
      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={`Edit ${editing?.email || "user"}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
            <Button
              disabled={saveEdit.isPending}
              onClick={() => saveEdit.mutate({ id: editing.id, ...editForm })}
            >
              {saveEdit.isPending ? "Saving…" : "Save changes"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Full name"
            value={editForm.full_name}
            onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
            placeholder="Jane Doe"
          />
          <Select
            label="Role"
            value={editForm.role_id}
            options={roleOptions}
            onChange={(e) => setEditForm({ ...editForm, role_id: e.target.value })}
          />
          <div className="flex items-center justify-between rounded-lg border border-card-border px-3 py-2.5">
            <div>
              <div className="text-sm font-medium text-foreground">Active</div>
              <div className="text-xs text-muted">Disabled users cannot sign in.</div>
            </div>
            <Toggle
              checked={editForm.is_active}
              onChange={(v) => setEditForm({ ...editForm, is_active: v })}
            />
          </div>
        </div>
      </Modal>

      {/* Delete user — requires the admin to re-enter their password */}
      <Modal
        open={!!deleting}
        onClose={() => {
          setDeleting(null);
          setDelPassword("");
        }}
        title="Delete user"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setDeleting(null);
                setDelPassword("");
              }}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending || !delPassword}
              onClick={() => remove.mutate({ id: deleting.id, password: delPassword })}
            >
              {remove.isPending ? "Deleting…" : "Delete user"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2.5 text-sm text-red-500">
            <Icon icon="heroicons-outline:exclamation-triangle" className="text-base mt-0.5 shrink-0" />
            <span>
              This permanently deletes <strong>{deleting?.email}</strong> and revokes their access. This
              cannot be undone.
            </span>
          </div>
          <Input
            label="Confirm your password"
            type="password"
            value={delPassword}
            onChange={(e) => setDelPassword(e.target.value)}
            placeholder="Your account password"
            hint="Re-enter your own password to authorize this deletion."
          />
        </div>
      </Modal>
    </div>
  );
}
