"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button, Card, EmptyState, PageHeader, Spinner } from "@/web/kit";
import { api, apiError } from "@/web/api";

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return String(ts);
  const diff = Date.now() - d.getTime();
  const min = Math.round(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day}d ago`;
  return d.toLocaleString();
}

export default function NotificationsPage() {
  const qc = useQueryClient();

  const notifications = useQuery({
    queryKey: ["messaging-notifications"],
    queryFn: () =>
      api.get("/messaging/notifications", { params: { page_size: 100 } }).then((r) => r.data),
    refetchInterval: 15000,
  });

  const items = notifications.data?.items || [];
  const unread = items.filter((n) => !n.read);

  const markRead = useMutation({
    mutationFn: (id) => api.post(`/messaging/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["messaging-notifications"] }),
    onError: (e) => toast.error(apiError(e)),
  });

  const markAll = useMutation({
    mutationFn: () => Promise.all(unread.map((n) => api.post(`/messaging/notifications/${n.id}/read`))),
    onSuccess: () => {
      toast.success("All notifications marked read");
      qc.invalidateQueries({ queryKey: ["messaging-notifications"] });
    },
    onError: (e) => toast.error(apiError(e)),
  });

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="Alerts and updates from across the platform."
        actions={
          <Button
            variant="secondary"
            icon="heroicons-outline:check-circle"
            disabled={markAll.isPending || unread.length === 0}
            onClick={() => markAll.mutate()}
          >
            {markAll.isPending ? "Marking…" : `Mark all read${unread.length ? ` (${unread.length})` : ""}`}
          </Button>
        }
      />

      {notifications.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <Card className="p-2">
          <EmptyState
            icon="heroicons-outline:bell"
            title="You're all caught up"
            subtitle="New notifications will show up here."
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((n) => (
            <Card
              key={n.id}
              className={`p-4 flex items-start justify-between gap-4 ${
                n.read ? "" : "border-l-2 !border-l-foreground bg-hover"
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {!n.read && <span className="h-2 w-2 rounded-full bg-blue-600 shrink-0" />}
                  <p className="font-medium text-foreground text-foreground truncate">{n.title}</p>
                </div>
                {n.body && <p className="text-sm text-muted text-muted mt-1">{n.body}</p>}
                <p className="text-xs text-muted mt-2">{formatTime(n.ts)}</p>
              </div>
              {!n.read && (
                <Button
                  variant="ghost"
                  icon="heroicons-outline:check"
                  disabled={markRead.isPending}
                  onClick={() => markRead.mutate(n.id)}
                >
                  Mark read
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
