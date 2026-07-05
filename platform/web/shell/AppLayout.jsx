"use client";

import { useQuery } from "@tanstack/react-query";
import { Icon } from "@iconify/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { api } from "@/web/api";
import CommandPalette from "@/web/CommandPalette";
import { FullPageLoader } from "@/web/kit";
import Footer from "@/web/shell/Footer";
import Header from "@/web/shell/Header";
import { useAuth } from "@/web/auth";

// A banner shown to every signed-in user when an admin sets an announcement.
function AnnouncementBanner() {
  const { data } = useQuery({
    queryKey: ["public-settings"],
    queryFn: () => api.get("/settings/public").then((r) => r.data),
    staleTime: 30_000,
  });
  const text = data?.announcement?.trim();
  if (!text) return null;
  return (
    <div className="shrink-0 bg-amber-500/10 border-b border-amber-500/20 text-amber-500">
      <div className="w-full px-6 lg:px-8 py-2 flex items-center gap-2 text-[13px]">
        <Icon icon="heroicons-outline:megaphone" className="text-base shrink-0" />
        <span className="truncate">{text}</span>
      </div>
    </div>
  );
}

// Auth-guarded application shell: horizontal top nav + full-width content.
export default function AppLayout({ children }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anon") router.replace("/login");
  }, [status, router]);

  if (status !== "authed") {
    return <FullPageLoader label={status === "anon" ? "Redirecting" : "Loading"} />;
  }

  // Full-height shell: header + footer stay fixed, only <main> scrolls.
  return (
    <div className="h-screen flex flex-col bg-background">
      <Header />
      <AnnouncementBanner />
      <main className="flex-1 overflow-y-auto w-full px-6 lg:px-8 py-6">{children}</main>
      <Footer />
      <CommandPalette />
    </div>
  );
}
