"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/web/api";

// Static footer pinned to the bottom of the app shell (only the main content
// between the header and this footer scrolls). Uses the white-label app name.
export default function Footer() {
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: () => api.get("/branding").then((r) => r.data),
    staleTime: 60_000,
  });
  const name = data?.app_name || "wonin.ai";
  const year = new Date().getFullYear();

  return (
    <footer className="shrink-0 border-t border-card-border bg-background">
      <div className="w-full px-6 lg:px-8 py-3 flex items-center justify-between text-xs text-muted">
        <span>
          © {year} {name}. All rights reserved.
        </span>
        <span className="hidden sm:inline">Powered by wonin.ai</span>
      </div>
    </footer>
  );
}
