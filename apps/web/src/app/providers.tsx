"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HeroUIProvider } from "@heroui/system";
import { MotionConfig } from "framer-motion";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";

import { useReducedMotion } from "@/lib/client-store";
import { ServerWakeup } from "@/components/ServerWakeup";
import { ThemeProvider } from "@/context/ThemeContext";
import { isApiError } from "@/lib/api";

function HeroUI({ children }: { children: ReactNode }) {
  const router = useRouter();

  return (
    <HeroUIProvider locale="ru-RU" navigate={(path) => router.push(path)}>
      {children}
    </HeroUIProvider>
  );
}

// Toasts need nothing at first paint: the stack arrives in its own chunk.
const Toaster = dynamic(() => import("@/components/Toaster").then((m) => m.Toaster), { ssr: false });

export function Providers({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  // One client per browser tab; useState keeps it stable across re-renders.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Back on the tab: every list and open record is read again (#25). Old data stays on
            // screen while it loads; a form holding an older version meets the 409 dialog.
            // Navigating back and forth within a few seconds reuses what is on screen instead of re-asking.
            staleTime: 15_000,
            refetchOnWindowFocus: "always",
            refetchOnReconnect: "always",
            // A 4xx is not cured by repeating: show the answer at once.
            retry: (count, error) => !(isApiError(error) && error.status < 500 && error.status > 0) && count < 2,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {/* reducedMotion follows the OS live: under prefers-reduced-motion every transform / layout animation (ours and
          HeroUI's) is dropped and only opacity changes stay */}
      <MotionConfig reducedMotion={reduced ? "always" : "never"}>
        <HeroUI>
          <ThemeProvider>
            <Toaster />
            <ServerWakeup />
            {children}
          </ThemeProvider>
        </HeroUI>
      </MotionConfig>
    </QueryClientProvider>
  );
}
