/** List filters kept in the address: a default value is not written, so a clean list has a clean URL. */

export type UrlValue = string | null | boolean;
export type UrlShape = Record<string, UrlValue>;

export function readState<T extends UrlShape>(search: string, defaults: T): T {
  const params = new URLSearchParams(search);
  const out: UrlShape = { ...defaults };

  for (const [key, fallback] of Object.entries(defaults)) {
    const raw = params.get(key);

    if (raw === null) continue;
    out[key] = typeof fallback === "boolean" ? raw === "1" : raw;
  }

  return out as T;
}

/** The query string after `patch`; keys outside `defaults` (another control's) stay as they are. */
export function writeState<T extends UrlShape>(search: string, defaults: T, patch: Partial<T>): string {
  const params = new URLSearchParams(search);

  for (const [key, value] of Object.entries(patch)) {
    if (!(key in defaults)) continue;
    if (value === defaults[key] || value === null || value === "" || value === false) params.delete(key);
    else params.set(key, value === true ? "1" : String(value));
  }

  return params.toString();
}

export function readPage(search: string): number {
  const page = Number(new URLSearchParams(search).get("page"));

  return Number.isInteger(page) && page > 0 ? page : 1;
}

export function writePage(search: string, page: number): string {
  const params = new URLSearchParams(search);

  if (page > 1) params.set("page", String(page));
  else params.delete("page");

  return params.toString();
}
