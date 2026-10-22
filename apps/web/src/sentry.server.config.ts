// Server (Node) error monitoring; started by instrumentation.ts. No DSN = off.
import * as Sentry from "@sentry/nextjs";

import { DATA_COLLECTION, scrubBreadcrumb, scrubEvent, TRACES_SAMPLE_RATE } from "./lib/monitoring";

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: "production",
    release: process.env.NEXT_PUBLIC_SENTRY_RELEASE || undefined,
    dataCollection: DATA_COLLECTION,
    tracesSampleRate: TRACES_SAMPLE_RATE,
    traceLifecycle: "static", // so beforeSendTransaction (the scrubber) applies
    beforeBreadcrumb: (crumb) => scrubBreadcrumb(crumb),
    beforeSend: (event) => scrubEvent(event),
    beforeSendTransaction: (event) => scrubEvent(event),
  });
}
