"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, ConfirmDialog, Input, Modal, PageHeader, Select, Spinner, Table } from "@/web/kit";
import { api, apiError } from "@/web/api";

const EMPTY = { name: "", role_id: "" };

function fmtDate(v) {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d) ? "—" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function ApiKeysPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [revealed, setRevealed] = useState(null); // the newly-created key object with raw `key`
  const [copied, setCopied] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const keys = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.get("/auth/api-keys", { params: { page_size: 100 } }).then((r) => r.data),
  });
  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => api.get("/auth/roles", { params: { page_size: 100 } }).then((r) => r.data),
  });
  const roleOptions = (roles.data?.items || []).map((r) => ({ value: r.id, label: r.name }));

  const create = useMutation({
    mutationFn: (body) => api.post("/auth/api-keys", body).then((r) => r.data),
    onSuccess: (data) => {
      toast.success("API key created");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
      setOpen(false);
      setForm(EMPTY);
      setRevealed(data);
      setCopied(false);
    },
    onError: (e) => toast.error(apiError(e)),
  });
  const revoke = useMutation({
    mutationFn: (id) => api.delete(`/auth/api-keys/${id}`),
    onSuccess: () => {
      toast.success("API key revoked");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
      setConfirm(null);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  function handleRevoke(row) {
    setConfirm({
      title: "Revoke API key",
      message: <>Revoke <strong>{row.name}</strong>? Applications using it will stop working.</>,
      confirmLabel: "Revoke key",
      onConfirm: () => revoke.mutate(row.id),
    });
  }

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(revealed.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }

  const columns = [
    {
      key: "name",
      label: "Name",
      render: (k) => <div className="font-medium">{k.name}</div>,
    },
    {
      key: "prefix",
      label: "Key",
      render: (k) => (
        <span className="font-mono text-xs text-muted text-muted">{k.prefix}…</span>
      ),
    },
    {
      key: "role",
      label: "Role",
      render: (k) => k.role?.name || "—",
    },
    {
      key: "created_at",
      label: "Created",
      render: (k) => <span className="text-muted">{fmtDate(k.created_at)}</span>,
    },
    {
      key: "last_used_at",
      label: "Last used",
      render: (k) => <span className="text-muted">{fmtDate(k.last_used_at)}</span>,
    },
    {
      key: "is_active",
      label: "Status",
      render: (k) => <Badge color={k.is_active ? "green" : "slate"}>{k.is_active ? "Active" : "Revoked"}</Badge>,
    },
    {
      key: "actions",
      label: "",
      render: (k) =>
        k.is_active ? (
          <Button
            variant="danger"
            icon="heroicons-outline:trash"
            onClick={() => handleRevoke(k)}
          >
            Revoke
          </Button>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader
        title="API Keys"
        subtitle="Programmatic access tokens for the inference API and integrations."
        actions={<Button variant="success" icon="heroicons-outline:plus" onClick={() => setOpen(true)}>Create key</Button>}
      />
      <Card className="p-2">
        {keys.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : (
          <Table columns={columns} rows={keys.data?.items} />
        )}
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Create API key"
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="success"
              disabled={create.isPending || !form.name || !form.role_id}
              onClick={() => create.mutate(form)}
            >
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Production integration"
          />
          <Select
            label="Role"
            value={form.role_id}
            options={[{ value: "", label: "Select a role…" }, ...roleOptions]}
            onChange={(e) => setForm({ ...form, role_id: e.target.value })}
          />
        </div>
      </Modal>

      <Modal
        open={!!revealed}
        onClose={() => setRevealed(null)}
        title="API key created"
        footer={<Button onClick={() => setRevealed(null)}>Done</Button>}
      >
        <div className="space-y-4">
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 px-3 py-2.5 text-sm text-amber-700 dark:text-amber-400">
            <Icon icon="heroicons-outline:exclamation-triangle" className="text-base mt-0.5 shrink-0" />
            <span>Copy this key now — you won't be able to see it again.</span>
          </div>
          <div>
            <span className="block text-sm font-medium text-muted text-muted mb-1">Secret key</span>
            <div className="flex items-stretch gap-2">
              <div className="flex-1 min-w-0 rounded-lg border border-card-border border-card-border bg-hover bg-background/40 px-3 py-2.5">
                <code className="block font-mono text-xs text-foreground text-foreground break-all">
                  {revealed?.key}
                </code>
              </div>
              <Button
                variant="secondary"
                icon={copied ? "heroicons-outline:check" : "heroicons-outline:clipboard"}
                onClick={copyKey}
              >
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={revoke.isPending} />
    </div>
  );
}
