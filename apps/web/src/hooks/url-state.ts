"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";

import { type UrlShape, readPage, readState, writePage, writeState } from "@/lib/url-state";

function replace(query: string) {
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

/** `useState` for list filters that lives in the address: Back from a card returns to the same
 * list. `defaults` must be a constant. The setter takes the whole object or only what changed. */
export function useUrlState<T extends UrlShape>(defaults: T): [T, (patch: Partial<T>) => void] {
  const search = useSearchParams().toString();
  const value = useMemo(() => readState(search, defaults), [search, defaults]);
  // the address is read at the time of the call: two setters in one handler both apply
  const set = useCallback(
    (patch: Partial<T>) => replace(writeState(window.location.search, defaults, patch)),
    [defaults],
  );

  return [value, set];
}

export function useUrlPage(): [number, (page: number) => void] {
  const page = readPage(useSearchParams().toString());
  const set = useCallback((next: number) => replace(writePage(window.location.search, next)), []);

  return [page, set];
}
