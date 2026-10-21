import { NextResponse, type NextRequest } from "next/server";

import { allowed, MAX_ENVELOPE_BYTES, tunnelTarget } from "@/lib/sentry-tunnel";

// Public by design (see lib/sentry-tunnel.ts): proxy.ts lets /monitoring through without a session.
export async function POST(request: NextRequest) {
  const ip = request.headers.get("x-vercel-forwarded-for")?.split(",")[0]?.trim() || "local";
  if (!allowed(ip)) return new NextResponse(null, { status: 429 });
  const length = Number(request.headers.get("content-length") ?? 0);
  if (length > MAX_ENVELOPE_BYTES) return new NextResponse(null, { status: 413 });
  const body = await request.text();
  if (body.length > MAX_ENVELOPE_BYTES) return new NextResponse(null, { status: 413 });
  const target = tunnelTarget(body, process.env.NEXT_PUBLIC_SENTRY_DSN);
  if (!target) return new NextResponse(null, { status: 400 });
  try {
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
