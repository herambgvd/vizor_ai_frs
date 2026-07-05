"use client";

import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Spinner, Table } from "@/web/kit";
import { api, apiError } from "@/web/api";
import { useAuth } from "@/web/auth";

const PAGE_SIZE = 25;

function formatTs(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

const ACTION_COLORS = {
  create: "green",
  update: "amber",
  delete: "red",
  revoke: "red",
  login: "blue",
  logout: "slate",
};

function actionColor(action) {
  const key = (action || "").toLowerCase();
  for (const [needle, color] of Object.entries(ACTION_COLORS)) {
    if (key.includes(needle)) return color;
  }
  return "slate";
}

// Human-readable phrasing per action code.
const ACTION_VERB = {
  "auth.login": "Signed in",
  "auth.logout": "Signed out",
  "user.create": "Created user",
  "user.update": "Updated user",
  "user.delete": "Deleted user",
  "role.create": "Created role",
  "role.update": "Updated role",
  "role.delete": "Deleted role",
  "apikey.create": "Created API key",
  "apikey.revoke": "Revoked API key",
  "branding.update": "Updated branding",
};

// Turn a raw entry into a plain-English sentence, pulling the specific target
// (name/email) out of `meta` so it reads like "Created user jane@example.com".
function describe(r) {
  const base = ACTION_VERB[r.action] || humanizeAction(r.action);
  const m = r.meta || {};
  const detail = m.email || m.name || m.title || null;
  return detail ? `${base} · ${detail}` : base;
}

function humanizeAction(action) {
  if (!action) return "Activity";
  const [obj, verb] = action.split(".");
  const v = verb ? verb.charAt(0).toUpperCase() + verb.slice(1) : "";
  return `${v} ${obj}`.trim();
}

// Admin-only card: view/adjust audit retention and purge old entries now.
function RetentionCard() {
  const qc = useQueryClient();
  const info = useQuery({
    queryKey: ["audit-retention"],
    queryFn: () => api.get("/audit/retention").then((r) => r.data),
  });
  const [days, setDays] = useState("");
  const [confirm, setConfirm] = useState(null);
  useEffect(() => {
    if (info.data) setDays(String(info.data.retention_days ?? 0));
  }, [info.data]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["audit-retention"] });
    qc.invalidateQueries({ queryKey: ["audit"] });
  };

  const savePolicy = useMutation({
    mutationFn: () => api.put("/settings", { values: { audit_retention_days: Number(days) || 0 } }),
    onSuccess: () => {
      invalidate();
      toast.success("Retention policy saved");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const purge = useMutation({
    mutationFn: () => api.post("/audit/purge", {}),
    onSuccess: (r) => {
      invalidate();
      setConfirm(null);
      toast.success(`Purged ${r.data.deleted} entr${r.data.deleted === 1 ? "y" : "ies"}`);
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const policyDays = Number(days) || 0;

  return (
    <Card className="p-5 mb-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Data retention</h2>
          <p className="text-xs text-muted mt-0.5">
            {info.data ? `${info.data.total} entries stored.` : "—"} Automatically delete entries
            older than the window below. 0 keeps them forever.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div className="w-40">
            <Input
              label="Retention (days)"
              type="number"
              min="0"
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
          </div>
          <Button variant="primary" disabled={savePolicy.isPending} onClick={() => savePolicy.mutate()}>
            {savePolicy.isPending ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="danger"
            icon="heroicons-outline:trash"
            disabled={purge.isPending || policyDays <= 0}
            title={policyDays <= 0 ? "Set a positive retention window first" : "Delete entries older than the window now"}
            onClick={() =>
              setConfirm({
                title: "Purge audit entries",
                message: `Permanently delete audit entries older than ${policyDays} days? This cannot be undone.`,
                confirmLabel: "Purge now",
                onConfirm: () => purge.mutate(),
              })
            }
          >
            {purge.isPending ? "Purging…" : "Purge now"}
          </Button>
        </div>
      </div>
      <ConfirmDialog state={confirm} onClose={() => setConfirm(null)} pending={purge.isPending} />
    </Card>
  );
}

export default function AuditPage() {
  const { can } = useAuth();
  const [page, setPage] = useState(1);

  const audit = useQuery({
    queryKey: ["audit", page],
    queryFn: () =>
      api.get("/audit", { params: { page, page_size: PAGE_SIZE } }).then((r) => r.data),
    placeholderData: keepPreviousData,
    // Always show the latest entries when landing on this page (no stale cache).
    staleTime: 0,
    refetchOnMount: "always",
  });

  const data = audit.data;
  const items = data?.items || [];

  const columns = [
    {
      key: "ts",
      label: "Time",
      render: (r) => <span className="text-muted text-muted">{formatTs(r.ts)}</span>,
    },
    {
      key: "actor_email",
      label: "Actor",
      render: (r) => <span className="font-medium">{r.actor_email || "—"}</span>,
    },
    {
      key: "action",
      label: "Action",
      render: (r) => <Badge color={actionColor(r.action)}>{r.action || "—"}</Badge>,
    },
    {
      key: "activity",
      label: "Activity",
      render: (r) => <span className="text-foreground">{describe(r)}</span>,
    },
  ];

  return (
    <div>
      <PageHeader title="Audit log" subtitle="A read-only record of actions taken across the platform." />
      {can("settings.manage") && <RetentionCard />}
      <Card className="p-2">
        {audit.isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon="heroicons-outline:document-text"
            title="No audit entries yet"
            subtitle="Actions performed in the app will appear here."
          />
        ) : (
          <Table columns={columns} rows={items} />
        )}
      </Card>

      {items.length > 0 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted">
            Page {data?.page ?? page}
            {data?.pages ? ` of ${data.pages}` : ""}
            {data?.total != null ? ` · ${data.total} entries` : ""}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              icon="heroicons-outline:chevron-left"
              disabled={!data?.has_prev || audit.isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Prev
            </Button>
            <Button
              variant="secondary"
              disabled={!data?.has_next || audit.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
