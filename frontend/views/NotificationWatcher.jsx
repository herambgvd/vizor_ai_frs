"use client";

// Watches the in-app notification feed and raises a top-level toast for each newly
// arrived notification (camera offline/online, etc.). Shares the header bell's query
// key so both stay in sync; the bell's unread badge updates from the same data.

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/web/api";

export default function NotificationWatcher() {
  const seen = useRef(null); // Set of ids we've already surfaced; null until first load

  const { data } = useQuery({
    queryKey: ["notifications-bell"],
    queryFn: () => api.get("/messaging/notifications", { params: { page_size: 10 } }).then((r) => r.data),
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    const items = data?.items || [];
    // First load: remember what already exists, don't toast the backlog.
    if (seen.current === null) {
      seen.current = new Set(items.map((n) => n.id));
      return;
    }
    // Oldest → newest so a burst toasts in order.
    for (const n of [...items].reverse()) {
      if (seen.current.has(n.id)) continue;
      seen.current.add(n.id);
      const t = (n.title || "").toLowerCase();
      const opts = { description: n.body || undefined };
      // Camera-offline alert stays until the operator dismisses it; everything else
      // auto-dismisses (5s from the global Toaster default).
      if (t.includes("offline")) toast.error(n.title || "Alert", { ...opts, duration: Infinity });
      else if (t.includes("online") || t.includes("back")) toast.success(n.title || "Recovered", opts);
      else toast(n.title || "Notification", opts);
    }
  }, [data]);

  return null;
}
