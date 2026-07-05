"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Icon } from "@iconify/react";

import { Badge, Button, Card, PageHeader, Spinner, Textarea } from "@/web/kit";
import { api, apiError } from "@/web/api";

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusBadge(lic) {
  if (lic.dev) return <Badge color="slate">Dev / unlicensed</Badge>;
  if (lic.is_expired) return <Badge color="red">Expired</Badge>;
  return <Badge color="green">Active</Badge>;
}

export default function LicensePage() {
  const qc = useQueryClient();
  const [token, setToken] = useState("");

  const license = useQuery({
    queryKey: ["license"],
    queryFn: () => api.get("/license").then((r) => r.data),
  });

  const apply = useMutation({
    mutationFn: (body) => api.post("/license", body),
    onSuccess: () => {
      toast.success("License updated");
      qc.invalidateQueries({ queryKey: ["license"] });
      setToken("");
    },
    onError: (e) => toast.error(apiError(e)),
  });

  const lic = license.data;

  return (
    <div>
      <PageHeader
        title="License"
        subtitle="Review your license status and apply renewals."
      />

      {license.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Status */}
          <div className="lg:col-span-2 space-y-6">
            <Card className="p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted">
                    Licensed to
                  </p>
                  <h3 className="text-lg font-semibold text-foreground text-foreground mt-0.5">
                    {lic?.client || "—"}
                  </h3>
                </div>
                {statusBadge(lic || {})}
              </div>

              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <Stat
                  icon="heroicons-outline:calendar-days"
                  label="Expires"
                  value={fmtDate(lic?.expires_at)}
                />
                <Stat
                  icon="heroicons-outline:video-camera"
                  label="Cameras"
                  value={lic?.limits?.cameras ?? "—"}
                />
                <Stat
                  icon="heroicons-outline:circle-stack"
                  label="Storage"
                  value={lic?.limits?.storage_gb != null ? `${lic.limits.storage_gb} GB` : "—"}
                />
              </div>

              {lic?.dev && (
                <div className="mt-5 flex items-start gap-2 rounded-lg bg-hover bg-hover px-4 py-3 text-sm text-muted text-muted">
                  <Icon
                    icon="heroicons-outline:information-circle"
                    className="text-base mt-0.5 shrink-0"
                  />
                  <span>
                    Running in development mode — the app is unlicensed and all limits are
                    ignored. Apply a signed token below to activate a production license.
                  </span>
                </div>
              )}
            </Card>

            {/* Modules */}
            <Card className="p-6">
              <h3 className="text-base font-semibold text-foreground mb-3">Modules</h3>
              {lic?.modules?.length ? (
                <div className="flex flex-wrap gap-2">
                  {lic.modules.map((m) => (
                    <Badge key={m} color="indigo">
                      {m}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted">No modules enabled.</p>
              )}
            </Card>

            {/* Features */}
            <Card className="p-6">
              <h3 className="text-base font-semibold text-foreground mb-3">Features</h3>
              {lic?.features && Object.keys(lic.features).length ? (
                <ul className="space-y-2">
                  {Object.entries(lic.features).map(([key, val]) => {
                    const on = Boolean(val);
                    return (
                      <li key={key} className="flex items-center gap-2 text-sm">
                        <Icon
                          icon={on ? "heroicons-outline:check-circle" : "heroicons-outline:x-circle"}
                          className={`text-base ${on ? "text-green-500" : "text-muted text-muted"}`}
                        />
                        <span className="text-foreground text-foreground">{key}</span>
                        {typeof val !== "boolean" && (
                          <span className="ml-auto text-muted">{String(val)}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-sm text-muted">No features listed.</p>
              )}
            </Card>
          </div>

          {/* Update license */}
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted mb-2">
              Update license
            </p>
            <Card className="p-6 space-y-4">
              <Textarea
                label="Signed license token"
                rows={8}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste your signed license token here…"
                className="font-mono text-xs"
              />
              <Button
                icon="heroicons-outline:key"
                className="w-full"
                disabled={apply.isPending || !token.trim()}
                onClick={() => apply.mutate({ token: token.trim() })}
              >
                {apply.isPending ? "Applying…" : "Apply"}
              </Button>
              <p className="text-xs text-muted">
                The token is verified and hot-swapped instantly. Expired tokens are rejected.
              </p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-card-border border-card-border px-4 py-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10 bg-blue-500/15 text-blue-400 text-blue-400">
        <Icon icon={icon} className="text-lg" />
      </div>
      <div>
        <p className="text-xs text-muted">{label}</p>
        <p className="font-medium text-foreground text-foreground">{value}</p>
      </div>
    </div>
  );
}
