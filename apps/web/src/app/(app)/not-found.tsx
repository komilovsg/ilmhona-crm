import type { Metadata } from "next";

import { NotFoundScreen } from "@/components/NotFoundScreen";
import { ERROR_COPY } from "@/lib/error-copy";

export const metadata: Metadata = { title: ERROR_COPY.notFound.title };

/** notFound() inside the app: the sidebar and header stay, only the page area says 404. */
export default function AppNotFound() {
  return <NotFoundScreen inShell />;
}
