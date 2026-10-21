"use client";

import clsx from "clsx";

import type { Tone } from "@/lib/sales";

const TONES: Record<Tone, string> = {
  default: "bg-default-100 text-default-700",
  primary: "bg-primary/10 text-brand-text",
  secondary: "bg-secondary/15 text-secondary-600 dark:text-secondary-500",
  success: "bg-success/15 text-success-700 dark:text-success",
  warning: "bg-warning/15 text-warning-700 dark:text-warning",
  danger: "bg-danger/15 text-danger-600 dark:text-danger",
};

/**
 * A status changed in place: a native select dressed as a chip (works with a thumb, keyboard and
 * screen readers alike). `busy` keeps the control in the layout while the change is saved.
 */
export function InlineSelect({
  label,
  value,
  options,
  tone,
  disabled,
  busy,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  tone: Tone;
  disabled?: boolean;
  busy?: boolean;
  onChange: (value: string) => void;
}) {
  const list = options.includes(value) ? options : [value, ...options];

  return (
    <select
      aria-busy={busy}
      aria-label={label}
      className={clsx(
        "h-8 max-w-full cursor-pointer appearance-none rounded-full border-0 py-0 pl-3 pr-3 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-focus",
        "disabled:cursor-default disabled:opacity-100",
        TONES[tone],
        busy && "opacity-60",
      )}
      disabled={disabled || busy}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {list.map((o) => (
        <option key={o} className="bg-content1 text-foreground" value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
