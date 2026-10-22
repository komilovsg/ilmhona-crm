"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { MonthStatus } from "@/lib/payment-month";

const POLL_MS = 3000;
/** The hold lives 120 s on the server: refresh it well before that while the form is open. */
const REFRESH_HOLD_MS = 30_000;

/**
 * The live state of the month a payment form is filling in: what is entered, by whom, and who
 * else is entering a payment right now. While `enabled`, polls every 3 s (paused in a hidden tab),
 * takes the month's hold when it is free and keeps it fresh; drops it when the month changes or
 * the form closes. The hold is only a hint for the others: the server rule decides.
 */
export function usePaymentMonth(enrollmentId: string | null, month: number | null, enabled: boolean) {
  const key = enabled && enrollmentId && month ? `${enrollmentId}:${month}` : null;
  const [state, setState] = useState<{ key: string; status: MonthStatus } | null>(null);
  const tickRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    if (!key || !enrollmentId || !month) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let running = false;
    let held = false;
    let heldAt = 0;
    const params = { enrollment_id: enrollmentId, month_no: String(month) };

    const tick = async () => {
      clearTimeout(timer);
      if (!alive || running) return;
      if (document.hidden) return; // resumes on visibilitychange
      running = true;
      try {
        let status = await api<MonthStatus>("/api/v1/payments/month", { params });
        if (alive && !status.held_by && !status.full && (!status.mine || Date.now() - heldAt > REFRESH_HOLD_MS)) {
          status = await api<MonthStatus>("/api/v1/payments/month/hold", {
            method: "POST",
            body: { enrollment_id: enrollmentId, month_no: month },
          });
          if (status.acquired) {
            held = true;
            heldAt = Date.now();
          }
        }
        if (alive) setState({ key, status });
      } catch {
        // a failed poll keeps the last state; the next one tries again
      } finally {
        running = false;
        if (alive) timer = setTimeout(() => void tick(), POLL_MS);
      }
    };
    const onVisible = () => {
      if (!document.hidden) void tick();
    };

    tickRef.current = () => void tick();
    void tick();
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      alive = false;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      tickRef.current = () => undefined;
      if (held) void api("/api/v1/payments/month/hold", { method: "DELETE", params }).catch(() => undefined);
    };
  }, [key, enrollmentId, month]);

  const refresh = useCallback(() => tickRef.current(), []);

  return { status: state && state.key === key ? state.status : null, refresh };
}
