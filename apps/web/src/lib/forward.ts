/** The header the API checks when PROXY_SHARED_SECRET is set (apps/api/app/core/proxy.py). */
export const PROXY_SECRET_HEADER = "x-proxy-secret";
/** The one header the API believes for the client address, set here (never by the browser). */
export const CLIENT_IP_HEADER = "x-client-ip";

// Forwarding headers a client could send to spoof its address: dropped before we forward, so the
// API only ever sees the address we put in CLIENT_IP_HEADER below.
const CLIENT_FORWARDING_HEADERS = [
  "x-forwarded-for",
  "forwarded",
  "x-real-ip",
  "x-client-ip",
  "x-vercel-forwarded-for",
];

/**
 * The real client address as Vercel's own edge recorded it. These headers are set by Vercel and
 * overwrite anything the browser sent, so they cannot be forged; `x-forwarded-for` can be, so it
 * is not used. Empty when running without Vercel (local dev): the API then falls back to the peer.
 */
export function trustedClientIp(incoming: Headers): string {
  const vercel = incoming.get("x-vercel-forwarded-for") ?? incoming.get("x-real-ip");
  return vercel?.split(",")[0]?.trim() ?? "";
}

/**
 * Request headers for an `/api/*` call leaving through the next.config rewrite: the browser's,
 * minus any address-forwarding header it tried to set, plus the shared secret that proves the
 * request came through this proxy and the trusted client address. Server side only
 * (PROXY_SHARED_SECRET, never NEXT_PUBLIC_).
 */
export function apiRequestHeaders(
  incoming: Headers,
  clientIp: string = "",
  secret: string | undefined = process.env.PROXY_SHARED_SECRET,
): Headers {
  const headers = new Headers(incoming);
  headers.delete(PROXY_SECRET_HEADER);
  for (const h of CLIENT_FORWARDING_HEADERS) headers.delete(h);
  const value = secret?.split(",")[0]?.trim();
  if (value) {
    headers.set(PROXY_SECRET_HEADER, value);
  }
  if (clientIp) {
    headers.set(CLIENT_IP_HEADER, clientIp);
  }
  return headers;
}
