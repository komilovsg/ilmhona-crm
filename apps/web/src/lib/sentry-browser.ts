// The browser side of Sentry, loaded lazily (instrumentation-client.ts, report-error.ts). Named
// imports only: a dynamic `import("@sentry/nextjs")` keeps the whole namespace, which put the
// Session Replay recorder and the feedback widget into the bundle; this way they are tree-shaken.
import { breadcrumbsIntegration, captureException, init } from "@sentry/nextjs";

import { DATA_COLLECTION, scrubBreadcrumb, scrubEvent, TRACES_SAMPLE_RATE } from "./monitoring";

export { captureException };

export function start(dsn: string): void {
  init({
    dsn,
    tunnel: "/monitoring",
    environment: "production",
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE || undefined,
    dataCollection: DATA_COLLECTION,
    tracesSampleRate: TRACES_SAMPLE_RATE,
    // no console, no DOM (clicks, input) breadcrumbs, no session pings; fetch/xhr/history stay, scrubbed below
    integrations: (defaults) =>
      defaults
        .filter((i) => !["Breadcrumbs", "Console", "BrowserSession"].includes(i.name))
        .concat(breadcrumbsIntegration({ dom: false })),
    beforeBreadcrumb: (crumb) => scrubBreadcrumb(crumb),
    beforeSend: (event) => scrubEvent(event),
    beforeSendTransaction: (event) => scrubEvent(event),
  });
}
