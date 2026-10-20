import { useEffect, useRef, useState, type FormEvent } from "react";

/**
 * Single-flight guard: while one run is in flight, further calls are ignored. The flag is
 * synchronous (not React state), so two calls in the same tick start exactly one run.
 */
export function singleFlight(run: () => Promise<unknown>): () => Promise<void> {
  let busy = false;

  return async () => {
    if (busy) return;
    busy = true;
    try {
      await run();
    } catch {
      // the mutation's own onError shows the message
    } finally {
      busy = false;
    }
  };
}

/**
 * The one submit pattern for forms and confirm buttons: `const submit = useSubmit(() => m.mutateAsync(), !valid)`,
 * then `onSubmit={submit}` and `onPress={() => submit()}`. Pair with `isLoading={m.isPending}`.
 */
export function useSubmit(run: () => Promise<unknown>, disabled = false) {
  const latest = useRef({ run, disabled });
  // the closure reads the ref only when a submit happens, never during render
  // eslint-disable-next-line react-hooks/refs
  const [guard] = useState(() => singleFlight(() => latest.current.run()));

  useEffect(() => {
    latest.current = { run, disabled };
  });

  return (event?: FormEvent) => {
    event?.preventDefault();
    if (!latest.current.disabled) void guard();
  };
}
