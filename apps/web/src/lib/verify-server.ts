import { headers } from "next/headers";

import { CLIENT_IP_HEADER, PROXY_SECRET_HEADER, trustedClientIp } from "./forward";
import { normalizeCode, type CheckResult, type PublicCertificate } from "./verify";

/** Ask the API about a code, server side, with the proxy secret and the visitor's address (rate limit). */
export async function checkCertificate(raw: string): Promise<CheckResult> {
  const code = normalizeCode(raw);
  if (!code) return { kind: "not_found" };
  const h = new Headers({ accept: "application/json" });
  const secret = process.env.PROXY_SHARED_SECRET?.split(",")[0]?.trim();
  if (secret) h.set(PROXY_SECRET_HEADER, secret);
  const ip = trustedClientIp(await headers());
  if (ip) h.set(CLIENT_IP_HEADER, ip);
  try {
    const res = await fetch(`${process.env.API_URL ?? "http://localhost:8200"}/api/v1/public/certificates/${code}`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (res.status === 404) return { kind: "not_found" };
    if (res.status === 429) return { kind: "limit" };
    if (!res.ok) return { kind: "error" };
    return { kind: "found", cert: (await res.json()) as PublicCertificate };
  } catch {
    return { kind: "error" };
  }
}
