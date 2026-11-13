import clsx from "clsx";

import { monthKind, monthStateLabel, type MonthKind, type MonthState } from "@/lib/payment-month";

const KIND: Record<MonthKind, string> = {
  paid: "bg-success/15 text-success-700 dark:text-success",
  awaiting: "border border-dashed border-warning bg-warning/15 text-warning-700 dark:text-warning",
  unpaid: "bg-danger/15 text-danger",
  future: "bg-default-100 text-default-500",
};

const LEGEND: { kind: MonthKind; text: string }[] = [
  { kind: "paid", text: "оплачен" },
  { kind: "awaiting", text: "ожидает подтверждения" },
  { kind: "unpaid", text: "не оплачен" },
  { kind: "future", text: "не наступил" },
];

/**
 * The months of an enrollment as small numbered marks: оплачен (green), ожидает подтверждения (amber, dashed),
 * не оплачен (red: the month began, not covered), не наступил (grey). Partial months are spelled out below.
 * `onPick` makes the months that still take a payment (started, not covered) buttons; `legend` spells
 * the colours out under the marks.
 */
export function MonthStates({
  states,
  className,
  legend,
  onPick,
}: {
  states: MonthState[];
  className?: string;
  legend?: boolean;
  onPick?: (month: number) => void;
}) {
  if (!states.length) return null;
  // spelled out: partial months and old-system overpayments («переплата N TJS»)
  const partial = states.filter((s) => (s.state === "частично" && s.started !== false) || Number(s.overpaid ?? 0) > 0);
  const present = new Set(states.map(monthKind));

  return (
    <div className={clsx("text-xs", className)}>
      <ul aria-label="Месяцы" className="flex flex-wrap gap-1">
        {states.map((s) => {
          const kind = monthKind(s);
          const tap = !!onPick && kind === "unpaid";
          const text = `Месяц ${s.month_no}: ${monthStateLabel(s)}`;
          const cls = clsx(
            "flex items-center justify-center rounded-md px-1 font-medium tabular-nums",
            onPick ? "h-10 min-w-10 text-sm md:h-6 md:min-w-6 md:text-xs" : "h-5 min-w-5",
            KIND[kind],
            tap && "cursor-pointer hover:ring-2 hover:ring-danger focus-visible:outline-2 focus-visible:outline-primary",
          );

          return (
            <li key={s.month_no}>
              {tap ? (
                <button aria-label={`Оплатить месяц ${s.month_no}`} className={cls} title={text} type="button" onClick={() => onPick(s.month_no)}>
                  {s.month_no}
                </button>
              ) : (
                <span aria-label={text} className={cls} role="img" title={text}>
                  {s.month_no}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {legend && (
        <ul aria-label="Обозначения" className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-default-500">
          {LEGEND.filter((l) => present.has(l.kind)).map((l) => (
            <li key={l.kind} className="flex items-center gap-1">
              <span aria-hidden className={clsx("size-3 rounded-sm", KIND[l.kind])} />
              {l.text}
            </li>
          ))}
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
