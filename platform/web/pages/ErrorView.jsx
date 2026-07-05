"use client";

import { Icon } from "@iconify/react";
import Link from "next/link";
import { useEffect } from "react";

// Theme-aware error boundary. Shows a clear message + the underlying error, with
// "Try again" (re-render the segment) and a route back to the dashboard.
export default function Error({ error, reset }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const status = error?.response?.status;
  const detail =
    error?.response?.data?.error?.message || error?.message || "An unexpected error occurred.";

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-5 h-12 w-12 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-500">
          <Icon icon="heroicons-outline:exclamation-triangle" className="text-2xl" />
        </div>
        <h1 className="text-lg font-semibold text-red-500">
          {status ? `Request failed (${status})` : "Something went wrong"}
        </h1>
        <p className="mt-2 text-sm text-muted">
          We couldn't load this page. You can try again, or head back to the dashboard.
        </p>

        <div className="mt-4 rounded-lg border border-card-border bg-card px-3 py-2.5 text-left">
          <code className="block font-mono text-xs text-muted break-all">{detail}</code>
        </div>

        <div className="mt-6 flex items-center justify-center gap-2">
          <button
            onClick={() => reset()}
            className="rounded-md bg-foreground text-background hover:opacity-90 px-4 py-2 text-sm font-medium transition"
          >
            Try again
          </button>
          <Link
            href="/"
            className="rounded-md border border-card-border text-foreground hover:bg-hover px-4 py-2 text-sm font-medium transition"
          >
            Go to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
