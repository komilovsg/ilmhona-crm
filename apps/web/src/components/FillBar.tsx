import { fillPercent } from "@/lib/education";
import type { Fill } from "@/lib/types";

/** «5/10» with a bar. Numbers come from the API (`fill`, computed by app/metrics). */
export function FillBar({ fill }: { fill: Fill }) {
  const pct = fillPercent(fill.enrolled, fill.capacity);
  const full = fill.enrolled >= fill.capacity;

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-default-500">Заполненность</span>
        <span className="font-medium tabular-nums">
          {fill.enrolled}/{fill.capacity}
        </span>
      </div>
      <div
        aria-label={`Заполнено ${pct}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={pct}
        className="h-2 overflow-hidden rounded-full bg-default-200"
        role="progressbar"
      >
        <div className={`h-full rounded-full ${full ? "bg-secondary" : "bg-primary"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
