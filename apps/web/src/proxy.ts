import { NextResponse, type NextRequest } from "next/server";

import { buildCsp, makeNonce } from "./lib/csp";
import { PROXY_SECRET_HEADER, apiRequestHeaders, trustedClientIp } from "./lib/forward";
import { isMissingStatus, recordApiPath } from "./lib/record-path";

const ACCESS_COOKIE = "ilm_access";
const PUBLIC_PAGES = new Set(["/login", "/forgot-password"]);
// Link-preview and install assets: reachable without a session (static, no data).
const PUBLIC_ASSETS = ["/opengraph-image", "/twitter-image", "/icon", "/apple-icon"];

/**
 * Attach a per-request CSP (src/lib/csp.ts) to a document response. The nonce is given to Next
 * through the request `Content-Security-Policy` header so Next stamps its own bootstrap scripts
 * with it, and returned on the response so the browser enforces the same policy.
 */
function withCsp(request: NextRequest, redirectTo?: URL, rewriteTo?: URL): NextResponse {
  const nonce = makeNonce();
  const proto = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol;
  const csp = buildCsp(nonce, { dev: process.env.NODE_ENV !== "production", https: proto.startsWith("https") });
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("content-security-policy", csp);
  const response = redirectTo
    ? NextResponse.redirect(redirectTo)
    : rewriteTo
      ? NextResponse.rewrite(rewriteTo, { request: { headers } })
      : NextResponse.next({ request: { headers } });
  response.headers.set("content-security-policy", csp);
  return response;
}

function isDocumentRequest(request: NextRequest): boolean {
  const h = request.headers;
  return !h.has("rsc") && !h.has("next-router-prefetch") && (h.get("accept") ?? "").includes("text/html");
}

/** Ask the API whether the record exists, with the visitor's own session. Any doubt means «exists». */
async function recordMissing(request: NextRequest, apiPath: string): Promise<boolean> {
  const headers = new Headers({ cookie: request.headers.get("cookie") ?? "", accept: "application/json" });
  const secret = process.env.PROXY_SHARED_SECRET?.split(",")[0]?.trim();
  if (secret) headers.set(PROXY_SECRET_HEADER, secret);
  try {
    const res = await fetch(`${process.env.API_URL ?? "http://localhost:8200"}${apiPath}`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return isMissingStatus(res.status);
  } catch {
    return false;
  }
}

/**
 * Optimistic check by cookie presence only; the API decides whether the session is valid
 * (a stale cookie gets a 401 there and the client goes to /login).
 */
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // API calls leave through the next.config rewrite: add the proxy secret and the trusted client
  // address, and drop any forwarding header the browser tried to set.
  if (pathname.startsWith("/api/")) {
    const ip = trustedClientIp(request.headers);
    return NextResponse.next({ request: { headers: apiRequestHeaders(request.headers, ip) } });
  }

  if (PUBLIC_ASSETS.some((p) => pathname.startsWith(p))) return NextResponse.next();

  const signedIn = request.cookies.has(ACCESS_COOKIE);

  if (pathname === "/") {
    return withCsp(request, new URL(signedIn ? "/dashboard" : "/login", request.url));
  }
  if (PUBLIC_PAGES.has(pathname)) {
    return signedIn
      ? withCsp(request, new URL("/dashboard", request.url))
      : withCsp(request);
  }

  if (!signedIn) return withCsp(request, new URL("/login", request.url));

  // A student or cohort that does not exist answers a real 404 (the page itself would stream a 200):
  // only for a full page load, not for client navigation or prefetch, which need no status.
  const record = isDocumentRequest(request) ? recordApiPath(pathname) : null;
  if (record && (await recordMissing(request, record))) {
    return withCsp(request, undefined, new URL("/not-found-record", request.url));
  }
  return withCsp(request);
}

export const config = {
  // Pages and /api (rewritten to the API by next.config.ts); assets are public.
  matcher: ["/((?!_next/|favicon.ico|.*\\..*).*)", "/api/:path*"],
};
