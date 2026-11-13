import clsx from "clsx";

import { monthKind, monthStateLabel, type MonthKind, type MonthState } from "@/lib/payment-month";

const KIND: Record<MonthKind, string> = {
  paid: "bg-success/15 text-success-700 dark:text-success",
  awaiting: "border border-dashed border-warning bg-warning/15 text-warning-700 dark:text-warning",
  unpaid: "bg-danger/15 text-danger",
  future: "bg-default-100 text-default-500",
};

/**
 * The months of an enrollment as small numbered marks: оплачен (green), ожидает подтверждения (amber, dashed),
 * не оплачен (red: the month began, not covered), не наступил (grey). Partial months are spelled out below.
 */
export function MonthStates({ states, className }: { states: MonthState[]; className?: string }) {
  if (!states.length) return null;
  // spelled out: partial months and old-system overpayments («переплата N TJS»)
  const partial = states.filter((s) => (s.state === "частично" && s.started !== false) || Number(s.overpaid ?? 0) > 0);

  return (
    <div className={clsx("text-xs", className)}>
      <ul aria-label="Месяцы" className="flex flex-wrap gap-1">
        {states.map((s) => (
          <li
            key={s.month_no}
            aria-label={`Месяц ${s.month_no}: ${monthStateLabel(s)}`}
            className={clsx("flex h-5 min-w-5 items-center justify-center rounded-md px-1 font-medium tabular-nums", KIND[monthKind(s)])}
            title={`Месяц ${s.month_no}: ${monthStateLabel(s)}`}
          >
            {s.month_no}
          </li>
        ))}
      </ul>
      {partial.map((s) => (
        <div key={s.month_no} className="mt-0.5 text-default-500">
          мес. {s.month_no}: {monthStateLabel(s)}
        </div>
      ))}
    </div>
  );
}
