"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";

import { AuthProvider } from "@/web/auth";
import { ThemeProvider, useTheme } from "@/web/theme";
import TitleSync from "@/web/TitleSync";

function ThemedToaster() {
  const { theme } = useTheme();
  return <Toaster theme={theme} position="bottom-right" richColors closeButton />;
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
