import type { FormEvent } from "react";

/**
 * The one submit pattern: a form handler that ignores Enter / double clicks while a request is
 * in flight. Pair it with `isLoading={pending}` on the submit button (HeroUI disables it then).
 */
export function submitOnce(pending: boolean, run: () => void) {
  return (event?: FormEvent) => {
    event?.preventDefault();
    if (!pending) run();
  };
}
