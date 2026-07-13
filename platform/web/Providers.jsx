"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";

import { AuthProvider } from "@/web/auth";
import { ThemeProvider, useTheme } from "@/web/theme";
import TitleSync from "@/web/TitleSync";

function ThemedToaster() {
  const { theme } = useTheme();
  // Auto-dismiss all toasts after 5s (individual toasts can override, e.g. a
  // camera-offline alert stays until acknowledged with duration: Infinity).
  return <Toaster theme={theme} position="bottom-right" richColors closeButton duration={5000} />;
}

// App-wide client providers: theme + TanStack Query + Auth + sonner toasts.
export default function Providers({ children }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 } },
      })
  );
  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <TitleSync />
        <AuthProvider>{children}</AuthProvider>
        <ThemedToaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
