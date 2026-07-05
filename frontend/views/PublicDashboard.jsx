"use client";

import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";

import { api } from "@/web/api";

function Stat({ label, value, icon, color }) {
  return (
    <div className="rounded-2xl border border-card-border bg-card p-6 text-center">
      <Icon icon={icon} className={`text-3xl mx-auto mb-2 ${color}`} />
      <div className="text-4xl font-semibold text-foreground tabular-nums">{value}</div>
      <div className="text-sm text-muted mt-1">{label}</div>
    </div>
  );
}

// Standalone, unauthenticated aggregate dashboard for a lobby/kiosk screen.
export default function PublicDashboard() {
  const dash = useQuery({
    queryKey: ["frs-public-dashboard"],
    queryFn: () => api.get("/frs/public/dashboard").then((r) => r.data),
    refetchInterval: 10000,
    retry: false,
  });
  const live = useQuery({
    queryKey: ["frs-public-live"],
    queryFn: () => api.get("/frs/public/live").then((r) => r.data.items),
    refetchInterval: 10000,
    retry: false,
    enabled: !dash.isError,
  });

  if (dash.isError) {
    return (
      <div className="min-h-dvh flex items-center justify-center text-muted">
        <div className="text-center"><Icon icon="heroicons-outline:lock-closed" className="text-4xl mx-auto mb-2" />The public dashboard is not enabled.</div>
      </div>
    );
  }
  const d = dash.data || {};
  return (
    <div className="min-h-dvh px-6 py-10 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold text-foreground text-center mb-8 flex items-center justify-center gap-2">
        <Icon icon="heroicons-outline:face-smile" /> Live Recognition
      </h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Stat label="Present now" value={d.present_15m ?? "—"} icon="heroicons-outline:users" color="text-green-500" />
        <Stat label="Recognised today" value={d.recognized_today ?? "—"} icon="heroicons-outline:check-badge" color="text-blue-400" />
        <Stat label="Unknown today" value={d.unknown_today ?? "—"} icon="heroicons-outline:question-mark-circle" color="text-amber-500" />
        <Stat label="Spoof attempts" value={d.spoof_today ?? "—"} icon="heroicons-outline:shield-exclamation" color="text-red-500" />
      </div>
      {live.data?.length > 0 && (
        <div className="rounded-2xl border border-card-border bg-card p-6">
          <div className="text-sm font-semibold text-foreground mb-3">Recent recognitions</div>
          <ul className="divide-y divide-card-border">
            {live.data.map((e, i) => (
              <li key={i} className="flex items-center justify-between py-2 text-sm">
                <span className="text-foreground flex items-center gap-2"><Icon icon="heroicons-outline:user-circle" className="text-muted" />{e.name}</span>
                <span className="text-muted">{e.time ? new Date(e.time).toLocaleTimeString() : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
