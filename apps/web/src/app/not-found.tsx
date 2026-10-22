import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { NotFoundScreen } from "@/components/NotFoundScreen";
import { ERROR_COPY } from "@/lib/error-copy";

export const metadata: Metadata = { title: ERROR_COPY.notFound.title };

/**
 * Every unknown URL lands here with a real 404 status (a catch-all page inside (app) would stream
 * and answer 200). The proxy sends visitors without a session to /login first, so whoever sees
 * this is signed in (a stale cookie gets the usual redirect to /login from the shell): the page
 * keeps the sidebar and header.
 */
export default function NotFound() {
  return (
    <AppShell>
      <NotFoundScreen inShell />
    </AppShell>
  );
}
