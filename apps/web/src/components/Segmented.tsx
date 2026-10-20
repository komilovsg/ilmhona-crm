"use client";

import clsx from "clsx";

export type SegmentOption<T extends string> = { key: T; label: string };

/** Tabs / mode switch: a pill group. Scrolls sideways instead of wrapping on a phone. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div
      aria-label={label}
      className={clsx("inline-flex max-w-full gap-1 overflow-x-auto rounded-xl bg-content2 p-1", className)}
      role="tablist"
    >
      {options.map((o) => (
        <button
          key={o.key}
          aria-selected={o.key === value}
          className={clsx(
            "shrink-0 whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            o.key === value ? "bg-content1 text-foreground shadow-sm" : "text-default-500 hover:text-foreground",
          )}
          role="tab"
          type="button"
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
