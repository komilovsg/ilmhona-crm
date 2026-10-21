/**
 * Send a caught error to monitoring (Sentry). For error boundaries (`error.tsx`,
 * `global-error.tsx`): `useEffect(() => reportError(error), [error])`. The SDK loads lazily, so
 * it stays out of the first-load bundle; without NEXT_PUBLIC_SENTRY_DSN this does nothing.
 */
export function reportError(error: unknown): void {
  if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return;
  void import("@sentry/nextjs").then((Sentry) => Sentry.captureException(error)).catch(() => {});
}
