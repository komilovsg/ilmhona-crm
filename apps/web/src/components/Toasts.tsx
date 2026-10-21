"use client";

import { ToastProvider } from "@heroui/toast";

import { useIsPhone, useReducedMotion } from "@/lib/client-store";
import { toastMotion, toastMotionReduced } from "@/lib/motion";

/** Desktop: top centre. Phone: bottom, above the tab bar, so a toast never covers a dialog's title. */
export function Toasts() {
  const phone = useIsPhone();
  const reduced = useReducedMotion();

  return (
    <ToastProvider
      placement={phone ? "bottom-center" : "top-center"}
      toastOffset={phone ? 76 : 12}
      toastProps={{ motionProps: reduced ? toastMotionReduced : toastMotion }}
    />
  );
}
