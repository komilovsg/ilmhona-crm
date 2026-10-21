"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { AuthSplit } from "@/components/AuthSplit";
import { ThemeToggle } from "@/components/ThemeToggle";

// Pages with the full brand frame; the others (change-password) stay a centred card.
const SPLIT_PAGES = new Set(["/login", "/forgot-password"]);

export default function AuthLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (SPLIT_PAGES.has(pathname)) return <AuthSplit>{children}</AuthSplit>;

  return (
    <div className="relative flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm">{children}</div>
    </div>
  );
}
