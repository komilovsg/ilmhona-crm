import { NextResponse, type NextRequest } from "next/server";

import { trustedClientIp } from "@/lib/forward";
import { allowed, readCapped, tunnelTarget } from "@/lib/sentry-tunnel";

// Public by design (see lib/sentry-tunnel.ts): proxy.ts lets /monitoring through without a session.
export async function POST(request: NextRequest) {
  if (!allowed(trustedClientIp(request.headers) || "local")) return new NextResponse(null, { status: 429 });
  const body = await readCapped(request);
  if (body === null) return new NextResponse(null, { status: 413 });
  const target = tunnelTarget(body, process.env.NEXT_PUBLIC_SENTRY_DSN);
  if (!target) return new NextResponse(null, { status: 400 });
  try {
    // only the envelope: no cookies, auth or forwarding headers of the caller go upstream
    await fetch(target, {
      method: "POST",
      body,
      headers: { "content-type": "application/x-sentry-envelope" },
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // monitoring must never turn into an error of its own
  }
  return new NextResponse(null, { status: 200 });
}
