"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { type UrlShape, readPage, readState, writePage, writeState } from "@/lib/url-state";

/** The queries this module has put into the address and the router has not reported back yet.
 * The router trails a fast typist: its «new» address may be three letters old, and that must not
 * overwrite the input. One registry for every hook on the page, since they share the address. */
const own = { queries: new Set<string>(), last: "" };

function replace(query: string) {
  own.queries.add(query);
  own.last = query;
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

/** State that also lives in the address. The value on screen is React state (typing never waits
 * for the router) and the address follows it; an address somebody else set (Back, a menu link)
 * is read back. */
function useAddress<V>(read: (search: string) => V): [V, (next: (cur: V) => V, query: (next: V) => string) => void] {
  const search = useSearchParams().toString();
  const [value, setValue] = useState(() => read(search));
  const [seen, setSeen] = useState(search);

  if (seen !== search) {
    setSeen(search);
    if (!own.queries.has(search)) setValue(read(search));
  }

  useEffect(() => {
    // the router has caught up with our latest write: nothing older can arrive any more
    if (own.last === search) own.queries.clear();
    else own.queries.delete(search);
  }, [search]);

  const set = useCallback((next: (cur: V) => V, query: (next: V) => string) => {
    setValue((cur) => {
      const value = next(cur);

      // the address is read at the time of the call: two setters in one handler both apply
      replace(query(value));

      return value;
    });
  }, []);

  return [value, set];
}

/** `useState` for list filters kept in the address: Back from a card returns to the same list, a
 * link to the bare section clears it. `defaults` must be a constant. The setter takes the whole
 * object or only what changed. */
export function useUrlState<T extends UrlShape>(defaults: T): [T, (patch: Partial<T>) => void] {
  const read = useCallback((search: string) => readState(search, defaults), [defaults]);
  const [value, write] = useAddress(read);
  const set = useCallback(
    (patch: Partial<T>) =>
      write(
        (cur) => ({ ...cur, ...patch }),
        () => writeState(window.location.search, defaults, patch),
      ),
    [write, defaults],
  );

  return [value, set];
}

export function useUrlPage(): [number, (page: number) => void] {
  const [page, write] = useAddress(readPage);
  const set = useCallback(
    (next: number) =>
      write(
        () => next,
        () => writePage(window.location.search, next),
      ),
    [write],
  );

  return [page, set];
}
