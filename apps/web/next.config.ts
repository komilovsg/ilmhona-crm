import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8200";

const nextConfig: NextConfig = {
  // The API sits behind the web origin, so the httpOnly cookies are first-party.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  // Signed-in pages must not be framed by another site (clickjacking).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Private app behind a login: nothing to index (robots.txt says the same).
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
