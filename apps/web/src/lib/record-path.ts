const DETAIL = /^\/(students|cohorts)\/([^/]+)$/;

/**
 * Detail pages load their record in the browser, so an unknown id would answer 200 with the
 * client's «not found» state. The proxy asks the API first for a document request of one of these
 * pages (this gives the API path to ask), and answers a real 404 when the record is missing.
 */
export function recordApiPath(pathname: string): string | null {
  const m = pathname.match(DETAIL);
  return m ? `/api/v1/${m[1]}/${m[2]}` : null;
}

/** 404 (no such record) and 422 (not even an id) mean missing; anything else (401, 5xx, down) lets the page load. */
export function isMissingStatus(status: number): boolean {
  return status === 404 || status === 422;
}
