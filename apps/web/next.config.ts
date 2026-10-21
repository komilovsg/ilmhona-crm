import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8200";

const nextConfig: NextConfig = {
  // The API sits behind the web origin, so the httpOnly cookies are first-party.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  // The full Content-Security-Policy is set per request in src/proxy.ts (it needs a nonce).
  // These static headers apply to every path, including static assets the proxy does not cover.
  async headers() {
    return [
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

export default nextConfig;
