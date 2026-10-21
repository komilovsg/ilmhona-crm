"use client";

import { useId } from "react";
import clsx from "clsx";
import { motion } from "framer-motion";

import { SPRING_SLIDE } from "@/lib/motion";

export type SegmentOption<T extends string> = { key: T; label: string };

/**
 * Tabs / mode switch: a pill group. Scrolls sideways instead of wrapping on a phone. The active pill
 * slides to the chosen tab (shared layout animation: transform only, nothing else moves).
 */
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
  const id = useId();

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
            "relative shrink-0 whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            o.key === value ? "text-foreground" : "text-default-500 hover:text-foreground",
          )}
          role="tab"
          type="button"
          onClick={() => onChange(o.key)}
        >
          {o.key === value && (
            <motion.span
              aria-hidden="true"
              className="absolute inset-0 rounded-lg bg-content1 shadow-sm"
              layoutId={`seg-${id}`}
              transition={SPRING_SLIDE}
            />
          )}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
