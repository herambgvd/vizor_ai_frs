"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { toast } from "sonner";

import { Button, Card, Spinner, Toggle } from "@/web/kit";
import { api, apiError } from "@/web/api";

function Row({ title, desc, children }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-card-border last:border-0">
      <div className="min-w-0"><div className="text-sm font-medium text-foreground">{title}</div>{desc && <div className="text-xs text-muted mt-0.5">{desc}</div>}</div>
      {children}
    </div>
  );
}

export default function FrsSettingsPage() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["frs-settings"], queryFn: () => api.get("/frs/settings").then((r) => r.data) });
  const update = useMutation({
    mutationFn: (patch) => api.put("/frs/settings", patch),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["frs-settings"] }); },
    onError: (e) => toast.error(apiError(e)),
  });
  const rotate = useMutation({
    mutationFn: () => api.post("/frs/settings/ingest-key/rotate"),
    onSuccess: () => { toast.success("Ingest key rotated"); qc.invalidateQueries({ queryKey: ["frs-settings"] }); },
    onError: (e) => toast.error(apiError(e)),
  });

  const s = settings.data;
  const copy = (t) => { navigator.clipboard?.writeText(t); toast.success("Copied"); };

  return (
    <div>
      {settings.isLoading || !s ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2 items-start">
          <Card className="p-6">
            <h2 className="text-sm font-semibold text-foreground mb-2">Feature toggles</h2>
            <Row title="Public dashboard" desc="Expose an unauthenticated, aggregate-only status screen.">
              <Toggle checked={s.public_dashboard_enabled} onChange={(v) => update.mutate({ public_dashboard_enabled: v })} />
            </Row>
            <Row title="Show names publicly" desc="Include person names on the public live feed.">
              <Toggle checked={s.public_show_names} onChange={(v) => update.mutate({ public_show_names: v })} />
            </Row>
            <Row title="Ingest API" desc="Allow external systems to post recognition events.">
              <Toggle checked={s.ingest_api_enabled} onChange={(v) => update.mutate({ ingest_api_enabled: v })} />
            </Row>
            {s.public_dashboard_enabled && (
              <a href="/public" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm text-blue-400 hover:underline mt-4">
                <Icon icon="heroicons-outline:arrow-top-right-on-square" /> Open public dashboard
              </a>
            )}
          </Card>

          <Card className="p-6 space-y-4">
            <h2 className="text-sm font-semibold text-foreground">Ingest API</h2>
            <div>
              <span className="block text-xs text-muted mb-1">Endpoint</span>
              <code className="block rounded-md border border-card-border bg-hover/40 px-3 py-2 text-xs text-foreground break-all">POST /api/v1/frs/ingest/event</code>
            </div>
            <div>
              <span className="block text-xs text-muted mb-1">API key (header <code>X-FRS-Ingest-Key</code>)</span>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-md border border-card-border bg-hover/40 px-3 py-2 text-xs text-foreground break-all">{s.ingest_api_key || "— not generated —"}</code>
                {s.ingest_api_key && <Button variant="ghost" icon="heroicons-outline:clipboard-document" title="Copy" onClick={() => copy(s.ingest_api_key)} />}
                <Button variant="secondary" icon="heroicons-outline:arrow-path" disabled={rotate.isPending} onClick={() => rotate.mutate()}>Rotate</Button>
              </div>
            </div>
            <div>
              <span className="block text-xs text-muted mb-1">Sample payload</span>
              <pre className="rounded-md border border-card-border bg-hover/40 px-3 py-2 text-[11px] text-foreground overflow-x-auto">{JSON.stringify(s.sample_ingest_payload, null, 2)}</pre>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
