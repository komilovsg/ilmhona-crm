/**
 * The /monitoring tunnel: browsers post Sentry envelopes to our own origin (CSP `connect-src
 * 'self'` stays strict, ad blockers do not drop them) and the server forwards them. It is
 * public (an error can happen before login), so it only ever forwards to the Sentry host of
 * OUR configured DSN, only envelopes that name that same DSN, within a size cap and a per-IP rate.
 */
export const MAX_ENVELOPE_BYTES = 200_000;
const RATE_PER_MINUTE = 30;

/** Upstream envelope URL when the envelope's first line names exactly our DSN; else null. */
export function tunnelTarget(envelope: string, ourDsn: string | undefined): string | null {
  if (!ourDsn) return null;
  try {
    const header = JSON.parse(envelope.slice(0, envelope.indexOf("\n")));
    if (header?.dsn !== ourDsn) return null;
    const dsn = new URL(ourDsn);
    const project = dsn.pathname.replace(/^\/+/, "");
    if (!/^\d+$/.test(project) || !dsn.hostname.endsWith(".sentry.io")) return null;
    return `https://${dsn.hostname}/api/${project}/envelope/`;
  } catch {
    return null;
  }
}

/** The body as text, or null past MAX_ENVELOPE_BYTES (counted in bytes, read as a stream, so a
 *  chunked request without a content-length is never buffered beyond the cap). */
export async function readCapped(request: Request): Promise<string | null> {
  if (Number(request.headers.get("content-length") ?? 0) > MAX_ENVELOPE_BYTES) return null;
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_ENVELOPE_BYTES) {
      await reader.cancel().catch(() => {});
      return null;
    }
    chunks.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(chunks));
}

const hits = new Map<string, { count: number; reset: number }>();

/** Fixed-window limit per client address. Per server instance (best effort), which is enough
 *  to stop a flood from one source; Sentry's own quota is the backstop. */
export function allowed(ip: string, now: number = Date.now()): boolean {
  if (hits.size > 5000) hits.clear();
  const hit = hits.get(ip);
  if (!hit || hit.reset <= now) {
    hits.set(ip, { count: 1, reset: now + 60_000 });
    return true;
  }
  hit.count += 1;
  return hit.count <= RATE_PER_MINUTE;
}
