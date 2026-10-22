import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8200";

const nextConfig: NextConfig = {
  // Error-monitoring release = the deployed commit (same sha for browser and server events).
  env: { NEXT_PUBLIC_SENTRY_RELEASE: process.env.VERCEL_GIT_COMMIT_SHA ?? "" },
  // The API sits behind the web origin, so the httpOnly cookies are first-party.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  // The full Content-Security-Policy is set per request in src/proxy.ts (it needs a nonce).
  // These static headers apply to every path, including static assets the proxy does not cover.
  async headers() {
    return [
      // /api/* answers carry Cache-Control: no-store from src/proxy.ts (headers() does not reach a proxied response).
      // Hashed build output (/_next/static) is immutable by default; these public files keep their name, so a week.
      ...["/brand/:path*", "/icon-192.png", "/icon-512.png", "/icon-maskable-192.png", "/icon-maskable-512.png"].map((source) => ({
        source,
        headers: [{ key: "Cache-Control", value: "public, max-age=604800, stale-while-revalidate=86400" }],
      })),
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          // HTTPS only (the app is served over TLS on Vercel); two years, with subdomains.
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          // Private app behind a login: nothing to index (robots.txt says the same).
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

// Source maps go to Sentry only when SENTRY_AUTH_TOKEN is set at build time (Vercel env, never in
// the repo), and the uploaded maps are deleted from the build output: they are never served.
export default async function config(): Promise<NextConfig> {
  if (!process.env.SENTRY_AUTH_TOKEN) return nextConfig;
  const { withSentryConfig } = await import("@sentry/nextjs/config");
  return withSentryConfig(nextConfig, {
    org: process.env.SENTRY_ORG,
    project: process.env.SENTRY_PROJECT,
    authToken: process.env.SENTRY_AUTH_TOKEN,
    release: { name: process.env.VERCEL_GIT_COMMIT_SHA },
    sourcemaps: { deleteSourcemapsAfterUpload: true },
    telemetry: false,
    silent: true,
  });
}
