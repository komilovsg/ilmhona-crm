import clsx from "clsx";

import { monthStateLabel, type MonthState } from "@/lib/payment-month";

/**
 * The months of an enrollment as small numbered marks: оплачен (green), частично (amber, with
 * «A из B» spelled out below), не оплачен (grey). Pending payments count, like the payment rule.
 */
export function MonthStates({
  states,
  className,
  legend,
  onPick,
}: {
  states: MonthState[];
  className?: string;
  /** Spell the colours out under the marks (not only a tooltip). */
  legend?: boolean;
  /** Makes every month that still takes a payment a button. */
  onPick?: (month: number) => void;
}) {
  if (!states.length) return null;
  // spelled out: partial months and old-system overpayments («переплата N TJS»)
  const partial = states.filter((s) => s.state === "частично" || Number(s.overpaid ?? 0) > 0);

  return (
    <div className={clsx("text-xs", className)}>
      <ul aria-label="Месяцы" className="flex flex-wrap gap-1">
        {states.map((s) => {
          const tap = !!onPick && s.state !== "оплачен";
          const cls = clsx(
            "flex items-center justify-center rounded-md px-1 font-medium tabular-nums",
            onPick ? "h-8 min-w-8 text-sm md:h-6 md:min-w-6 md:text-xs" : "h-5 min-w-5",
            s.state === "оплачен" && "bg-success/15 text-success-700 dark:text-success",
            s.state === "частично" && "bg-warning/20 text-warning-700 dark:text-warning",
            s.state === "не оплачен" && "bg-default-100 text-default-500",
            Number(s.pending) > 0 && "outline-1 outline-dashed outline-offset-1 outline-warning",
            tap && "cursor-pointer hover:ring-2 hover:ring-primary focus-visible:outline-2 focus-visible:outline-primary",
          );
          const text = `Месяц ${s.month_no}: ${monthStateLabel(s)}${Number(s.pending) > 0 ? " · ожидает подтверждения" : ""}`;

          return (
            <li key={s.month_no}>
              {tap ? (
                <button aria-label={`Оплатить месяц ${s.month_no}`} className={cls} title={text} type="button" onClick={() => onPick(s.month_no)}>
                  {s.month_no}
                </button>
              ) : (
                <span aria-label={text} className={cls} title={text} role="img">
                  {s.month_no}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {legend && (
        <ul aria-label="Обозначения" className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-default-500">
          <li className="flex items-center gap-1">
            <span aria-hidden className="size-3 rounded-sm bg-success/15 ring-1 ring-success/40" />
            оплачен
          </li>
          <li className="flex items-center gap-1">
            <span aria-hidden className="size-3 rounded-sm bg-warning/20" />
            частично
          </li>
          <li className="flex items-center gap-1">
            <span aria-hidden className="size-3 rounded-sm outline-1 outline-dashed outline-warning" />
            ожидает
          </li>
          <li className="flex items-center gap-1">
            <span aria-hidden className="size-3 rounded-sm bg-default-100 ring-1 ring-default-300" />
            не оплачен
          </li>
        </ul>
      )}
      {partial.map((s) => (
        <div key={s.month_no} className="mt-0.5 text-default-500">
          мес. {s.month_no}: {monthStateLabel(s)}
        </div>
      ))}
    </div>
  );
}
