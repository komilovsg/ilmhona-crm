import { errorText } from "./api-errors";

/** An API error as thrown by `api()`: HTTP status + the code of the problem+json body. */
export type ApiError = {
  status: number;
  code: string;
  params?: Record<string, unknown>;
  /** Rejected fields of a 422 (last name of each `loc`). */
  fields?: string[];
};

export function isApiError(error: unknown): error is ApiError {
  return typeof error === "object" && error !== null && "status" in error && "code" in error;
}

export function messageOf(error: unknown): string {
  return errorText(isApiError(error) ? error.code : undefined);
}

type Options = { method?: string; body?: unknown; params?: Record<string, string | undefined> };

let refreshing: Promise<boolean> | null = null;

/** One refresh at a time: the rotating token must not be spent twice by parallel requests. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: { "X-Requested-With": "ilm" },
    credentials: "same-origin",
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });

  return refreshing;
}

function leave(path: string) {
  if (typeof window !== "undefined" && window.location.pathname !== path)
    window.location.assign(path);
}

const AUTH_PATHS = ["/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout"];

/**
 * Same-origin JSON fetch to the API (`/api/*` is rewritten to it by next.config.ts).
 * A state change carries the CSRF header the API requires. An expired access token is
 * refreshed once and the request repeated; a dead session sends the user to /login, a
 * pending temporary password to /change-password.
 */
export async function api<T = void>(path: string, options: Options = {}, retried = false): Promise<T> {
  const { method = "GET", body, params } = options;
  const query = new URLSearchParams(
    Object.entries(params ?? {}).filter((e): e is [string, string] => !!e[1]),
  ).toString();
  const headers: Record<string, string> = {};

  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-Requested-With"] = "ilm";

  let response: Response;

  try {
    response = await fetch(query ? `${path}?${query}` : path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw { status: 0, code: "network_error" } satisfies ApiError;
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null);

  if (response.ok) return data as T;

  const code: string = data?.code ?? "internal_error";

  if (response.status === 401 && !AUTH_PATHS.includes(path)) {
    if (!retried && (await refreshSession())) return api<T>(path, options, true);
    // Drop the stale cookies first: with an access cookie left, /login would bounce back.
    await fetch("/api/v1/auth/logout", { method: "POST", headers: { "X-Requested-With": "ilm" } }).catch(
      () => undefined,
    );
    leave("/login");
  }
  if (code === "password_change_required") leave("/change-password");

  throw {
    status: response.status,
    code,
    params: data?.params,
    fields: (data?.errors as { loc: string[] }[] | undefined)?.map((e) => String(e.loc.at(-1))),
  } satisfies ApiError;
}
