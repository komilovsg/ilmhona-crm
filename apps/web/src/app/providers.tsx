"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HeroUIProvider } from "@heroui/system";
import { ToastProvider } from "@heroui/toast";
import { MotionConfig } from "framer-motion";
import { useRouter } from "next/navigation";

import { useIsPhone } from "@/lib/client-store";
import { ServerWakeup } from "@/components/ServerWakeup";
import { ThemeProvider } from "@/context/ThemeContext";
import { isApiError } from "@/lib/api";
import { toastMotion } from "@/lib/motion";

function HeroUI({ children }: { children: ReactNode }) {
  const router = useRouter();

  return (
    <HeroUIProvider locale="ru-RU" navigate={(path) => router.push(path)}>
      {children}
    </HeroUIProvider>
  );
}

/** Desktop: top centre. Phone: bottom, above the tab bar, so a toast never covers a dialog's title. */
function Toasts() {
  const phone = useIsPhone();

  return (
    <ToastProvider
      placement={phone ? "bottom-center" : "top-center"}
      toastOffset={phone ? 76 : 12}
      toastProps={{ motionProps: toastMotion }}
    />
  );
}

export function Providers({ children }: { children: ReactNode }) {
  // One client per browser tab; useState keeps it stable across re-renders.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Back on the tab: every list and open record is read again (#25). Old data stays on
            // screen while it loads; a form holding an older version meets the 409 dialog.
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
      {/* reducedMotion="user": under prefers-reduced-motion every transform / layout animation (ours and
          HeroUI's) is dropped and only opacity changes stay */}
      <MotionConfig reducedMotion="user">
        <HeroUI>
          <ThemeProvider>
            <Toasts />
            <ServerWakeup />
            {children}
          </ThemeProvider>
        </HeroUI>
      </MotionConfig>
    </QueryClientProvider>
  );
}
