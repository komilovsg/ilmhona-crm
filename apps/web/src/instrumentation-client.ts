// Browser error monitoring. The SDK is imported dynamically so it is its own chunk, outside
// the first-load JS; no DSN (dev, tests) = nothing is loaded. No Session Replay, no feedback
// widget, no tracing integration. Setup: src/lib/sentry-browser.ts, scrubbing: src/lib/monitoring.ts.
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) void import("./lib/sentry-browser").then((s) => s.start(dsn));
