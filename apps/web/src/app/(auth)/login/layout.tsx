import type { Metadata } from "next";
import type { ReactNode } from "react";

import { loginMetadata } from "@/lib/site";

export const metadata: Metadata = loginMetadata;

export default function LoginLayout({ children }: { children: ReactNode }) {
  return children;
}
