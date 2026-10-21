"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { ThemeToggle } from "./ThemeToggle";

/** The glow of the owner's logo: bright cyan in the top-left corner, falling to the dark brand colour. */
const GLOW =
  "radial-gradient(circle at 0% 0%, #4fd3f7 0%, #1fa7d6 11%, #1b6f8c 27%, #14323f 50%, rgba(16,24,32,0) 78%), linear-gradient(160deg, #101820 0%, #0f151b 100%)";

/** Text wordmark until the SVG logo lands: «ilm» white, «hona» brand blue. */
function Wordmark({ className = "" }: { className?: string }) {
  return (
    <div aria-label="ilmhona" className={`font-bold leading-none tracking-tight ${className}`} role="img">
      <span className="text-white">ilm</span>
      <span className="text-[#00A0DC]">hona</span>
    </div>
  );
}

/**
 * Sign-in frame. Desktop: the brand panel on the left, the form on the right. Phone: a gradient
 * band with the wordmark, the form on a sheet below it. The form rises in once (not with reduced motion).
 */
export function AuthSplit({ children }: { children: ReactNode }) {
  const still = useReducedMotion();
  const rise = (delay: number) =>
    still
      ? {}
      : {
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] as const },
        };

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <aside className="relative flex h-44 flex-col justify-end overflow-hidden px-6 pb-9 md:h-auto md:min-h-dvh md:justify-between md:p-14" style={{ background: GLOW }}>
        <div className="hidden md:block" />
        <motion.div {...rise(0)}>
          <Wordmark className="text-4xl md:text-6xl" />
          <p className="mt-2 max-w-xs text-sm text-[#C9D6E0] md:mt-4 md:text-lg">
            Учёт студентов, потоков и оплат в одном месте.
          </p>
        </motion.div>
      </aside>

      <main className="relative -mt-5 rounded-t-3xl bg-background px-5 pb-10 pt-16 md:mt-0 md:flex md:items-center md:justify-center md:rounded-none md:px-10">
        <div className="absolute right-4 top-4">
          <ThemeToggle />
        </div>
        <motion.div className="mx-auto w-full max-w-sm" {...rise(0.12)}>
          {children}
        </motion.div>
      </main>
    </div>
  );
}
