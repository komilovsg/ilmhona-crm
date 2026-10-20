import { NextResponse, type NextRequest } from "next/server";

const ACCESS_COOKIE = "ilm_access";
const PUBLIC_PAGES = new Set(["/login"]);

/**
 * Optimistic check by cookie presence only; the API decides whether the session is valid
 * (a stale cookie gets a 401 there and the client goes to /login).
 */
export function proxy(request: NextRequest) {
  const signedIn = request.cookies.has(ACCESS_COOKIE);
  const { pathname } = request.nextUrl;

  if (pathname === "/") {
    return NextResponse.redirect(new URL(signedIn ? "/dashboard" : "/login", request.url));
  }
  if (PUBLIC_PAGES.has(pathname)) {
    return signedIn ? NextResponse.redirect(new URL("/dashboard", request.url)) : NextResponse.next();
  }

  return signedIn ? NextResponse.next() : NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Pages only: /api is rewritten to the API by next.config.ts, assets are public.
  matcher: ["/((?!api/|_next/|favicon.ico|.*\\..*).*)"],
};
