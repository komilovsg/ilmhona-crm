/**
 * Error-monitoring helpers shared by the browser, server and edge Sentry setups.
 * The database holds real personal data, so nothing is sent unscrubbed (docs/ops/monitoring.md):
 * no request bodies, cookies or query values, a short header allowlist, no user but the id, no
 * console or input breadcrumbs, and any phone number or e-mail inside a string is replaced.
 * Pure functions, no Sentry import: unit-tested in monitoring.test.ts.
 */
export const FILTERED = "[Filtered]";
export const TRACES_SAMPLE_RATE = 0.02;
const SAFE_HEADERS = new Set(["accept", "accept-language", "content-length", "content-type", "host", "user-agent"]);
// Event fields that are structure, not user text (ids and timestamps look like numbers).
const STRUCTURAL = new Set([
  "event_id", "timestamp", "start_timestamp", "release", "environment", "platform", "level",
  "type", "trace_id", "span_id", "parent_span_id", "sdk", "modules", "trace", "sample_rand",
]);
const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
// 9+ digits, optionally with + ( ) - . or spaces between them: a phone number in any format
const PHONE = /(?<![\w.])\+?\d(?:[\s().-]{0,2}\d){8,}(?![\w])/g;

/** Sentry v11 `dataCollection` (replaces `sendDefaultPii`): everything personal switched off. */
export const DATA_COLLECTION = {
  userInfo: false,
  cookies: false,
  httpHeaders: { allow: [...SAFE_HEADERS] },
  httpBodies: [],
  urlQueryParams: false,
  databaseQueryData: false,
  queues: false,
  stackFrameVariables: false,
  genAI: { inputs: false, outputs: false },
  graphQL: { document: false, variables: false },
};

type Json = Record<string, unknown>;

export function scrubText(value: string): string {
  return value.replace(EMAIL, FILTERED).replace(PHONE, FILTERED);
}

function scrub(value: unknown): unknown {
  if (typeof value === "string") return scrubText(value);
  if (Array.isArray(value)) return value.map(scrub);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, STRUCTURAL.has(k) ? v : scrub(v)]));
  }
  return value;
}

/** A URL reduced to origin + path: no query, no fragment. Relative and broken input reduce too. */
export function pathOnly(url: string): string {
  const cut = url.search(/[?#]/);
  return cut < 0 ? url : url.slice(0, cut);
}

function query(raw: string): string {
  return [...new URLSearchParams(raw).keys()].map((k) => `${k}=${FILTERED}`).join("&");
}

function request(req: Json): Json {
  const out: Json = { method: req.method };
  if (typeof req.url === "string") out.url = pathOnly(req.url);
  if (typeof req.query_string === "string" && req.query_string) out.query_string = query(req.query_string);
  const headers = (req.headers ?? {}) as Record<string, string>;
  out.headers = Object.fromEntries(Object.entries(headers).filter(([k]) => SAFE_HEADERS.has(k.toLowerCase())));
  return out; // no data, cookies, env
}

/** A breadcrumb with only its kind and a safe message; null drops it (console output). */
export function scrubBreadcrumb<T extends object>(crumb: T): T | null {
  const c = crumb as Json;
  if (c.category === "console") return null;
  const out: Json = { ...c };
  const data = (c.data ?? {}) as Json;
  // fetch / xhr: the path and the outcome, never the query, headers or bodies
  if (c.category === "fetch" || c.category === "xhr") {
    out.data = {
      method: data.method,
      status_code: data.status_code,
      url: typeof data.url === "string" ? pathOnly(data.url) : undefined,
    };
  } else if (c.category === "navigation") {
    out.data = {
      from: typeof data.from === "string" ? pathOnly(data.from) : undefined,
      to: typeof data.to === "string" ? pathOnly(data.to) : undefined,
    };
  } else {
    delete out.data;
  }
  return scrub(out) as T;
}

/** Everything personal removed from one event or transaction. */
export function scrubEvent<T extends object>(event: T): T {
  const e = { ...event } as Json;
  if (e.request) e.request = request(e.request as Json);
  const user = e.user as Json | undefined;
  if (user) e.user = user.id ? { id: user.id } : {};
  if (e.breadcrumbs) {
    const raw = e.breadcrumbs as Json[] | { values: Json[] };
    const list = Array.isArray(raw) ? raw : raw.values;
    e.breadcrumbs = list.map((b) => scrubBreadcrumb(b)).filter((b) => b !== null);
  }
  for (const k of ["server_name", "extra"]) delete e[k];
  return scrub(e) as T;
}
