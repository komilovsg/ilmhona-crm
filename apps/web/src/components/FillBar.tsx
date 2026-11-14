import { overBy } from "@/lib/capacity";
import { fillPercent } from "@/lib/education";
import type { Fill } from "@/lib/types";

/**
 * «5 / 10» with a bar. Numbers come from the API (`fill`, computed by app/metrics). Over the plan:
 * a warning chip with text, the bar stays at full width and gets an end marker.
 */
export function FillBar({ fill }: { fill: Fill }) {
  const pct = fillPercent(fill.enrolled, fill.capacity);
  const over = overBy(fill);
  const full = fill.enrolled >= fill.capacity;

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-2 text-xs">
        <span className="text-default-500">Заполненность</span>
        <span className="flex items-center gap-1.5">
          <span className="font-medium tabular-nums">
            {fill.enrolled} / {fill.capacity}
          </span>
          {over > 0 && (
            <span className="rounded-full bg-warning-100 px-2 py-0.5 font-medium text-warning-700 dark:bg-warning/20 dark:text-warning">
              сверх плана +{over}
            </span>
          )}
        </span>
      </div>
      <div
        aria-label={over > 0 ? `Заполнено ${fill.enrolled} из ${fill.capacity}, сверх плана +${over}` : `Заполнено ${pct}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={pct}
        className="relative h-2 overflow-hidden rounded-full bg-default-200"
        role="progressbar"
      >
        <div
          className={`h-full rounded-full ${over > 0 ? "bg-warning" : full ? "bg-secondary" : "bg-primary"}`}
          style={{ width: `${pct}%` }}
        />
        {over > 0 && <div className="absolute inset-y-0 right-0 w-1.5 bg-warning-700 dark:bg-warning-200" />}
      </div>
    </div>
  );
}
