// Security response headers on the frontend (HTML) tier — defence-in-depth
// alongside the backend middleware and the TLS reverse proxy. The authoritative
// Content-Security-Policy is set at the reverse proxy (where the real domain is
// known); these are the domain-independent OWASP/STQC baseline headers.
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "X-Permitted-Cross-Domain-Policies", value: "none" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained production server (server.js + trimmed node_modules) so the
  // prod image is small and needs no runtime install. Ignored by `next dev`.
  output: "standalone",
  // Next 16 runs on Turbopack by default. We have no custom bundler rules
  // (SVGs are rendered via @iconify at runtime, not imported as modules), so no
  // webpack/turbopack config is required.
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

module.exports = nextConfig;
