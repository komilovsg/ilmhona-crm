import { NextResponse, type NextRequest } from "next/server";

import { apiRequestHeaders } from "./lib/forward";

const ACCESS_COOKIE = "ilm_access";
const PUBLIC_PAGES = new Set(["/login"]);

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

  const signedIn = request.cookies.has(ACCESS_COOKIE);

  if (pathname === "/") {
    return NextResponse.redirect(new URL(signedIn ? "/dashboard" : "/login", request.url));
  }
  if (PUBLIC_PAGES.has(pathname)) {
    return signedIn ? NextResponse.redirect(new URL("/dashboard", request.url)) : NextResponse.next();
  }

  return signedIn ? NextResponse.next() : NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Pages and /api (rewritten to the API by next.config.ts); assets are public.
  matcher: ["/((?!_next/|favicon.ico|.*\\..*).*)", "/api/:path*"],
};
