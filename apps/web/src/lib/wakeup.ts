// Render's free tier sleeps: the first request after a pause can take 30–60 s. When a request
// is still unanswered after SLOW_MS and the server has not answered once yet in this tab, the
// app shows a full-screen «Сервер просыпается…» instead of an endless skeleton.
import { useSyncExternalStore } from "react";

export const SLOW_MS = 5000;

let awake = false;
let slow = 0;
let since = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

/** Call before a request; call the returned function when it ends (`answered`: the server replied). */
export function trackRequest(): (answered: boolean) => void {
  if (awake) return () => undefined;

  let flagged = false;
  const timer = setTimeout(() => {
    flagged = true;
    if (slow++ === 0) since = Date.now();
    emit();
  }, SLOW_MS);

  return (answered) => {
    clearTimeout(timer);
    if (answered) awake = true;
    if (flagged) slow--;
    if (flagged || answered) emit();
  };
}

function subscribe(listener: () => void) {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
}

/** True while the first requests have been waiting longer than SLOW_MS. */
export function useServerWaking(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => slow > 0 && !awake,
    () => false,
  );
}

export function wakingSince(): number {
  return since;
}
