"use client";

import { useEffect, useState } from "react";

import { useServerWaking, wakingSince } from "@/lib/wakeup";

const EXPECTED_MS = 60_000;

/** Full-screen notice while the sleeping API starts (first request > 5 s): friendly, with progress. */
export function ServerWakeup() {
  const waking = useServerWaking();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!waking) return;

    const tick = () => setElapsed(Date.now() - wakingSince());
    const timer = setInterval(tick, 500);

    return () => {
      clearInterval(timer);
      setElapsed(0);
    };
  }, [waking]);

  if (!waking) return null;

  const percent = Math.min(95, Math.round(((elapsed + 5000) / EXPECTED_MS) * 100));

  return (
    <div
      aria-live="polite"
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-4 bg-background px-6 text-center"
      role="status"
    >
      <h2 className="text-xl font-semibold">Сервер просыпается…</h2>
      <p className="max-w-sm text-default-600">
        Бесплатный сервер засыпает без работы. Обычно запуск занимает до минуты, потом всё будет быстро. Данные в безопасности.
      </p>
      <div
        aria-label="Запуск сервера"
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={percent}
        className="h-2 w-64 max-w-full overflow-hidden rounded-full bg-default-200"
        role="progressbar"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-sm text-default-500">Прошло: {Math.round(elapsed / 1000)} с</p>
    </div>
  );
}
