import type { Metadata } from "next";

import { NotFoundScreen } from "@/components/NotFoundScreen";
import { ERROR_COPY } from "@/lib/error-copy";

export const metadata: Metadata = { title: ERROR_COPY.notFound.title };

export default function NotFound() {
  return <NotFoundScreen />;
}
