import { NextResponse, type NextRequest } from "next/server";

import { buildCsp, makeNonce } from "./lib/csp";
import { apiRequestHeaders } from "./lib/forward";

const ACCESS_COOKIE = "ilm_access";
const PUBLIC_PAGES = new Set(["/login"]);
// Link-preview and install assets: reachable without a session (static, no data).
const PUBLIC_ASSETS = ["/opengraph-image", "/twitter-image", "/icon", "/apple-icon"];

/**
 * Attach a per-request CSP (src/lib/csp.ts) to a document response. The nonce is given to Next
 * through the request `Content-Security-Policy` header so Next stamps its own bootstrap scripts
 * with it, and returned on the response so the browser enforces the same policy.
 */
function withCsp(request: NextRequest, redirectTo?: URL): NextResponse {
  const nonce = makeNonce();
  const csp = buildCsp(nonce, { dev: process.env.NODE_ENV !== "production" });
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("content-security-policy", csp);
  const response = redirectTo
    ? NextResponse.redirect(redirectTo)
    : NextResponse.next({ request: { headers } });
  response.headers.set("content-security-policy", csp);
  return response;
}

/**
 * Optimistic check by cookie presence only; the API decides whether the session is valid
 * (a stale cookie gets a 401 there and the client goes to /login).
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // API calls leave through the next.config rewrite: add the proxy secret on the way.
  if (pathname.startsWith("/api/")) {
    return NextResponse.next({ request: { headers: apiRequestHeaders(request.headers) } });
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

  return signedIn ? withCsp(request) : withCsp(request, new URL("/login", request.url));
}

export const config = {
  // Pages and /api (rewritten to the API by next.config.ts); assets are public.
  matcher: ["/((?!_next/|favicon.ico|.*\\..*).*)", "/api/:path*"],
};
