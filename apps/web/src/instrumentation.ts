import type { Instrumentation } from "next";

export async function register() {
  if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return;
  if (process.env.NEXT_RUNTIME === "nodejs") await import("./sentry.server.config");
  if (process.env.NEXT_RUNTIME === "edge") await import("./sentry.edge.config");
}

// Errors thrown while rendering on the server or in route handlers (scrubbed in beforeSend).
export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
};
