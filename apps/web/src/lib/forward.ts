/** The header the API checks when PROXY_SHARED_SECRET is set (apps/api/app/core/proxy.py). */
export const PROXY_SECRET_HEADER = "x-proxy-secret";

/**
 * Request headers for an `/api/*` call leaving through the next.config rewrite: the browser's,
 * plus the shared secret that proves to the API the request came through this proxy. Server
 * side only (PROXY_SHARED_SECRET, never NEXT_PUBLIC_); a value the browser sent is dropped.
 */
export function apiRequestHeaders(
  incoming: Headers,
  secret: string | undefined = process.env.PROXY_SHARED_SECRET,
): Headers {
  const headers = new Headers(incoming);
  headers.delete(PROXY_SECRET_HEADER);
  const value = secret?.split(",")[0]?.trim();
  if (value) {
    headers.set(PROXY_SECRET_HEADER, value);
  }
  return headers;
}
