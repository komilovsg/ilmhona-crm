"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HeroUIProvider } from "@heroui/system";
import { ToastProvider } from "@heroui/toast";
import { useRouter } from "next/navigation";

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

export function Providers({ children }: { children: ReactNode }) {
  // One client per browser tab; useState keeps it stable across re-renders.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: true,
            // A 4xx is not cured by repeating: show the answer at once.
            retry: (count, error) => !(isApiError(error) && error.status < 500 && error.status > 0) && count < 2,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <HeroUI>
        <ThemeProvider>
          <ToastProvider placement="top-center" toastOffset={12} />
          <ServerWakeup />
          {children}
        </ThemeProvider>
      </HeroUI>
    </QueryClientProvider>
  );
}
