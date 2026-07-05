"use client";

import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import SystemResources from "@/web/SystemResources";
import { Badge, Card, PageHeader, Spinner } from "@/web/kit";
import { api } from "@/web/api";

const DEP_META = {
  database: { label: "Database", icon: "heroicons-outline:circle-stack" },
  redis: { label: "Redis", icon: "heroicons-outline:bolt" },
  storage: { label: "Object storage", icon: "heroicons-outline:server" },
};

export default function HealthPage() {
  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: () => api.get("/system/health").then((r) => r.data),
    refetchInterval: 10000,
  });

  const checks = health.data?.checks || {};
  const overall = health.data?.status;

  return (
    <div className="space-y-8">
      <PageHeader
        title="System health"
        subtitle="Live status of the platform's dependencies and host resources."
        actions={
          overall ? (
            <Badge color={overall === "healthy" ? "green" : "red"}>
              {overall === "healthy" ? "All systems operational" : "Degraded"}
            </Badge>
          ) : null
        }
      />

      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-3">Dependencies</h2>
        {health.isLoading ? (
          <Card className="p-2">
            <div className="flex justify-center py-12">
              <Spinner />
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {Object.entries(DEP_META).map(([key, meta]) => {
              const state = checks[key] || "unknown";
              const ok = state === "ok";
              return (
                <Card key={key} className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2 text-muted">
                      <Icon icon={meta.icon} className="text-lg" />
                      <span className="text-sm font-medium text-foreground">{meta.label}</span>
                    </div>
                    <Badge color={ok ? "green" : "red"}>{ok ? "Healthy" : "Down"}</Badge>
                  </div>
                  {!ok && <p className="text-xs text-red-500 break-all">{state}</p>}
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-3">Host resources</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <SystemResources />
        </div>
      </div>
    </div>
  );
}
