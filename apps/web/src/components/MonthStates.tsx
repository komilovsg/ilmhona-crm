import clsx from "clsx";

import { monthStateLabel, type MonthState } from "@/lib/payment-month";

/**
 * The months of an enrollment as small numbered marks: оплачен (green), частично (amber, with
 * «A из B» spelled out below), не оплачен (grey). Pending payments count, like the payment rule.
 */
export function MonthStates({ states, className }: { states: MonthState[]; className?: string }) {
  if (!states.length) return null;
  const partial = states.filter((s) => s.state === "частично");

  return (
    <div className={clsx("text-xs", className)}>
      <ul aria-label="Месяцы" className="flex flex-wrap gap-1">
        {states.map((s) => (
          <li
            key={s.month_no}
            aria-label={`Месяц ${s.month_no}: ${monthStateLabel(s)}`}
            className={clsx(
              "flex h-5 min-w-5 items-center justify-center rounded-md px-1 font-medium tabular-nums",
              s.state === "оплачен" && "bg-success/15 text-success-700 dark:text-success",
              s.state === "частично" && "bg-warning/20 text-warning-700 dark:text-warning",
              s.state === "не оплачен" && "bg-default-100 text-default-500",
            )}
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
