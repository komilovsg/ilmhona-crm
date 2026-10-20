import clsx from "clsx";

import { Bone } from "./Skeletons";

export type Stat = {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "success" | "warning" | "danger";
};

const TONE: Record<NonNullable<Stat["tone"]>, string> = {
  default: "",
  success: "text-success-600 dark:text-success",
  warning: "text-warning-600 dark:text-warning",
  danger: "text-danger",
};

const GRID = "mb-4 grid gap-3 sm:grid-cols-2";

function cols(count: number): string {
  return count >= 4 ? "lg:grid-cols-4" : count === 3 ? "lg:grid-cols-3" : "";
}

/** Numbers of a screen: a row of cards (label, value, hint), fixed line heights so nothing jumps. */
export function StatCards({ stats }: { stats: Stat[] }) {
  return (
    <div className={clsx(GRID, cols(stats.length))}>
      {stats.map((s) => (
        <div key={s.label} className="rounded-2xl bg-content1 p-4">
          <div className="h-4 text-xs leading-4 text-default-500">{s.label}</div>
          <div className={clsx("mt-1 h-7 truncate text-xl font-semibold leading-7", TONE[s.tone ?? "default"])}>
            {s.value}
          </div>
          <div className="mt-0.5 h-4 truncate text-xs leading-4 text-default-500">{s.hint ?? ""}</div>
        </div>
      ))}
    </div>
  );
}

/** Same boxes as `StatCards`, as bones. */
export function StatCardsSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div aria-hidden="true" className={clsx(GRID, cols(count))}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-2xl bg-content1 p-4">
          <Bone className="h-4 w-24" />
          <Bone className="mt-1 h-7 w-36" />
          <Bone className="mt-0.5 h-4 w-20" />
        </div>
      ))}
    </div>
  );
}
