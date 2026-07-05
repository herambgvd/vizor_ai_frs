"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { api } from "@/web/api";

// Keeps the browser tab title = branding app name, consistently.
// Next re-applies the static route metadata title on every navigation, so we
// depend on `pathname` to re-assert the branded title after each route change.
export default function TitleSync() {
  const pathname = usePathname();
  const { data } = useQuery({
    queryKey: ["branding"],
    queryFn: () => api.get("/branding").then((r) => r.data),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (data?.app_name) document.title = data.app_name;
  }, [data?.app_name, pathname]);

  return null;
}
