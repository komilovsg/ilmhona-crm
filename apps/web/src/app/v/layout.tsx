import type { Metadata } from "next";
import type { ReactNode } from "react";

import { IlmMark } from "@/components/brand/IlmMark";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Проверка сертификата",
  robots: { index: false, follow: false, nocache: true },
};

/** The public check page: no app shell, no session; the brand mark, the theme switch, one column. */
export default function VerifyLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-xl items-center justify-between gap-4 px-4 pt-5 sm:px-6 sm:pt-8">
        <div aria-label="ilmhona" className="flex items-center gap-2 text-xl font-bold leading-none tracking-tight text-foreground" role="img">
          <IlmMark className="text-[#00a0dc]" height={20} />
          <span>ilmhona</span>
        </div>
        <ThemeToggle />
      </header>
      <main className="mx-auto w-full max-w-xl flex-1 px-4 pb-12 pt-6 sm:px-6 sm:pt-10">{children}</main>
    </div>
  );
}
