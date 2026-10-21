/**
 * Content-Security-Policy for the app's HTML documents.
 *
 * `script-src` is locked to a per-request nonce plus `strict-dynamic`, so an injected inline
 * `<script>` or `onerror=` cannot run even if a name/note/comment were ever rendered unescaped
 * (defence in depth on top of React's escaping). `style-src` keeps `'unsafe-inline'` because
 * HeroUI and framer-motion set inline `style` attributes; inline styles cannot exfiltrate data.
 *
 * Development adds `'unsafe-eval'` (React Refresh) and `ws:` (HMR socket); production adds
 * `upgrade-insecure-requests`. The nonce is generated in `proxy.ts` per request and propagated
 * to Next through the request `Content-Security-Policy` header so Next nonces its own scripts.
 */
export function buildCsp(nonce: string, { dev }: { dev: boolean }): string {
  const script = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"];
  if (dev) script.push("'unsafe-eval'");
  const connect = ["'self'"];
  if (dev) connect.push("ws:");
  const directives: Record<string, string[] | null> = {
    "default-src": ["'self'"],
    "base-uri": ["'self'"],
    "script-src": script,
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'", "data:"],
    "connect-src": connect,
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
    "frame-src": ["'none'"],
    "object-src": ["'none'"],
    "worker-src": ["'self'", "blob:"],
    "manifest-src": ["'self'"],
    "upgrade-insecure-requests": dev ? null : [],
  };
  return Object.entries(directives)
    .filter(([, v]) => v !== null)
    .map(([k, v]) => (v && v.length ? `${k} ${v.join(" ")}` : k))
    .join("; ");
}

/** A URL-safe base64 nonce from 16 random bytes. */
export function makeNonce(): string {
  return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
}
