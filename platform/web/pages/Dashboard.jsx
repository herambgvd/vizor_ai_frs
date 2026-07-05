"use client";

import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import Link from "next/link";

import SystemResources from "@/web/SystemResources";
import { Card, PageHeader, Spinner } from "@/web/kit";
import { api } from "@/web/api";
import { useAuth } from "@/web/auth";

// Compact relative time: "just now" / "5m ago" / "3h ago" / a date.
function timeAgo(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const mins = (Date.now() - d.getTime()) / 60000;
  if (mins < 1) return "just now";
  if (mins < 60) return `${Math.floor(mins)}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

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

function describe(r) {
  const base =
    ACTION_VERB[r.action] ||
    (r.action ? r.action.split(".").reverse().join(" ") : "Activity");
  const m = r.meta || {};
  const detail = m.email || m.name || m.title || null;
  return detail ? `${base} · ${detail}` : base;
}

function actionIcon(action) {
  const a = (action || "").toLowerCase();
  if (a.includes("delete") || a.includes("revoke"))
    return { icon: "heroicons-outline:trash", color: "text-red-500" };
  if (a.includes("create")) return { icon: "heroicons-outline:plus", color: "text-green-500" };
  if (a.includes("login") || a.includes("logout"))
    return { icon: "heroicons-outline:arrow-right-on-rectangle", color: "text-blue-500" };
  return { icon: "heroicons-outline:pencil-square", color: "text-amber-500" };
}

// The Users metric tile — sized to match the resource gauges beside it.
function UsersCard({ value, loading }) {
  return (
    <Link href="/users" className="block">
      <Card className="p-4 h-full flex items-center gap-3 transition hover:border-muted">
        <div className="h-[58px] w-[58px] rounded-full bg-hover flex items-center justify-center shrink-0">
          <Icon icon="heroicons-outline:users" className="text-xl text-foreground" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">Users</div>
          {loading ? (
            <div className="h-6 w-10 mt-1 rounded bg-hover animate-pulse" />
          ) : (
            <div className="text-2xl font-semibold text-foreground leading-tight">{value}</div>
          )}
        </div>
      </Card>
    </Link>
  );
}

export default function DashboardPage() {
  const { user, can } = useAuth();

  const usersQ = useQuery({
    queryKey: ["users", "count"],
    queryFn: () => api.get("/auth/users", { params: { page_size: 1 } }).then((r) => r.data),
    enabled: can("user.read"),
  });
  const auditQ = useQuery({
    queryKey: ["audit", "recent"],
    queryFn: () => api.get("/audit", { params: { page_size: 6 } }).then((r) => r.data),
    enabled: can("audit.read"),
    staleTime: 0,
    refetchOnMount: "always",
  });

  const showUsers = can("user.read");
  const showActivity = can("audit.read");
  const recent = auditQ.data?.items || [];

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome, ${user?.full_name || user?.email}`}
        subtitle="Your platform at a glance — users, live resources and recent activity."
      />

      {/* Row 1 — Users + live host gauges, all on one line */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {showUsers && <UsersCard value={usersQ.data?.total ?? "—"} loading={usersQ.isLoading} />}
        <SystemResources />
      </div>

      {/* Row 2 — recent activity (leaves room for scenario widgets later) */}
      {showActivity && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-2 p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-foreground">Recent activity</h2>
              <Link href="/audit" className="text-xs text-muted hover:text-foreground transition">
                View all →
              </Link>
            </div>
            {auditQ.isLoading ? (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            ) : recent.length === 0 ? (
              <p className="text-sm text-muted py-6 text-center">No activity recorded yet.</p>
            ) : (
              <ul className="divide-y divide-card-border">
                {recent.map((r, i) => {
                  const ai = actionIcon(r.action);
                  return (
                    <li key={r.id || i} className="flex items-center gap-3 py-2.5">
                      <div className="h-8 w-8 rounded-full bg-hover flex items-center justify-center shrink-0">
                        <Icon icon={ai.icon} className={`text-base ${ai.color}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] text-foreground truncate">{describe(r)}</div>
                        <div className="text-xs text-muted truncate">{r.actor_email || "System"}</div>
                      </div>
                      <span className="text-xs text-muted shrink-0">{timeAgo(r.ts)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
