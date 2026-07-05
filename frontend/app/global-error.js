"use client";

// Catches errors in the root layout itself. It replaces the whole document, so it
// must render its own <html>/<body> and can't use the app's Tailwind/theme — hence
// inline styles (defaults to the dark palette).
export default function GlobalError({ error, reset }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#000",
          color: "#ededed",
          fontFamily: "system-ui, -apple-system, sans-serif",
          padding: 24,
        }}
      >
        <div style={{ maxWidth: 420, textAlign: "center" }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 8,
              background: "#fff",
              color: "#000",
              fontWeight: 700,
              fontSize: 18,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 20px",
            }}
          >
            N
          </div>
          <h1 style={{ fontSize: 18, fontWeight: 600, margin: 0, color: "#ef4444" }}>
            Something went wrong
          </h1>
          <p style={{ color: "#a1a1a1", fontSize: 14, marginTop: 8 }}>
            A critical error occurred while loading Neubit. Please try again.
          </p>
          {error?.message && (
            <div
              style={{
                marginTop: 16,
                border: "1px solid #262626",
                borderRadius: 8,
                background: "#0a0a0a",
                padding: "10px 12px",
                textAlign: "left",
              }}
            >
              <code style={{ fontFamily: "monospace", fontSize: 12, color: "#a1a1a1", wordBreak: "break-all" }}>
                {error.message}
              </code>
            </div>
          )}
          <button
            onClick={() => reset()}
            style={{
              marginTop: 20,
              background: "#fff",
              color: "#000",
              border: "none",
              borderRadius: 6,
              padding: "8px 16px",
              fontWeight: 500,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
