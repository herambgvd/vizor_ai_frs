import Link from "next/link";

// Theme-aware 404 page (renders inside RootLayout, so tokens + theme apply).
export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-md text-center">
        <div className="mx-auto mb-6 h-11 w-11 rounded-lg bg-white flex items-center justify-center text-black text-lg font-bold">
          N
        </div>
        <div className="text-7xl font-bold tracking-tight text-foreground">404</div>
        <h1 className="mt-3 text-lg font-semibold text-foreground">Page not found</h1>
        <p className="mt-2 text-sm text-muted">
          The page you're looking for doesn't exist or may have been moved.
        </p>
        <div className="mt-6 flex items-center justify-center gap-2">
          <Link
            href="/"
            className="rounded-md bg-foreground text-background hover:opacity-90 px-4 py-2 text-sm font-medium transition"
          >
            Go to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
