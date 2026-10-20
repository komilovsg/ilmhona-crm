import { useSyncExternalStore } from "react";

const noSubscribe = () => () => {};

/** `false` on the server and during hydration, `true` afterwards. */
export function useIsHydrated(): boolean {
  return useSyncExternalStore(
    noSubscribe,
    () => true,
    () => false,
  );
}

/**
 * A value kept in the browser (localStorage, a class on <html>). The server renders
 * `serverValue`; the client switches to the stored one right after hydration and re-reads
 * it whenever `event` fires on window. Use this instead of setState-in-effect.
 */
export function useBrowserValue<T>(read: () => T, serverValue: T, event: string): T {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener(event, onChange);
      window.addEventListener("storage", onChange);

      return () => {
        window.removeEventListener(event, onChange);
        window.removeEventListener("storage", onChange);
      };
    },
    read,
    () => serverValue,
  );
}

/** Media query as a value (false on the server). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);

      mql.addEventListener("change", onChange);

      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Phone layout: below Tailwind's `md` (768 px). */
export function useIsPhone(): boolean {
  return useMediaQuery("(max-width: 767.98px)");
}
