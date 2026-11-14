import { overWarning, wouldExceed } from "@/lib/capacity";
import type { Fill } from "@/lib/types";

/** Inline warning before an enrollment that goes over the cohort's seats; the save button then reads «…всё равно». */
export function OverCapacityNotice({ fill }: { fill: Fill | undefined }) {
  if (!fill || !wouldExceed(fill)) return null;

  return (
    <p
      className="rounded-xl bg-warning-50 p-3 text-sm font-medium text-warning-700 dark:bg-warning/10 dark:text-warning"
      role="status"
    >
      {overWarning(fill)}
    </p>
  );
}
