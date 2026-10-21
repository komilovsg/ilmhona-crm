// Browser error monitoring. The SDK is imported dynamically so it is its own chunk, outside
// the first-load JS; no DSN (dev, tests) = nothing is loaded. No Session Replay, no feedback
// widget, no tracing integration. Scrubbing rules: src/lib/monitoring.ts.
if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  void Promise.all([import("@sentry/nextjs"), import("./lib/monitoring")]).then(([Sentry, m]) => {
    Sentry.init({
      dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
      tunnel: "/monitoring",
      environment: "production",
      release: process.env.NEXT_PUBLIC_SENTRY_RELEASE || undefined,
      dataCollection: m.DATA_COLLECTION,
      tracesSampleRate: m.TRACES_SAMPLE_RATE,
      // no console, no DOM (clicks, input) breadcrumbs, no session pings; fetch/xhr/history stay, scrubbed below
      integrations: (defaults) =>
        defaults
          .filter((i) => !["Breadcrumbs", "Console", "BrowserSession"].includes(i.name))
          .concat(Sentry.breadcrumbsIntegration({ dom: false })),
      beforeBreadcrumb: (crumb) => m.scrubBreadcrumb(crumb),
      beforeSend: (event) => m.scrubEvent(event),
      beforeSendTransaction: (event) => m.scrubEvent(event),
    });
  });
}
