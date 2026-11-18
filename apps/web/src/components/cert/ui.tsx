"use client";

import { useEffect, useState, type ReactNode } from "react";
import clsx from "clsx";

const FIELD =
  "h-8 w-full rounded-lg border border-divider bg-content2 px-2 text-sm text-foreground outline-none focus:border-primary disabled:opacity-50";

export function Row({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="mb-1 block text-xs text-default-500">{label}</span>
      {children}
    </label>
  );
}

/** A number input that keeps what the user types and commits a valid number on change / blur. */
export function NumField({
  label,
  value,
  onChange,
  step = 0.1,
  min,
  max,
  disabled,
  testId,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  step?: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  testId?: string;
}) {
  const shown = String(Math.round(value * 100) / 100);
  const [draft, setDraft] = useState<string | null>(null);

  return (
    <Row label={label}>
      <input
        className={FIELD}
        data-testid={testId}
        disabled={disabled}
        inputMode="decimal"
        max={max}
        min={min}
        step={step}
        type="number"
        value={draft ?? shown}
        onBlur={() => setDraft(null)}
        onChange={(e) => {
          setDraft(e.target.value);
          const n = parseFloat(e.target.value);

          if (Number.isFinite(n)) onChange(Math.min(max ?? Infinity, Math.max(min ?? -Infinity, n)));
        }}
      />
    </Row>
  );
}

export function TextField({ label, value, onChange, disabled, placeholder }: { label: string; value: string; onChange: (v: string) => void; disabled?: boolean; placeholder?: string }) {
  return (
    <Row label={label}>
      <input className={FIELD} disabled={disabled} placeholder={placeholder} type="text" value={value} onChange={(e) => onChange(e.target.value)} />
    </Row>
  );
}

export function SelectNative<T extends string | number>({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: T;
  options: { key: T; label: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <Row label={label}>
      <select
        className={FIELD}
        disabled={disabled}
        value={String(value)}
        onChange={(e) => onChange((typeof value === "number" ? Number(e.target.value) : e.target.value) as T)}
      >
        {options.map((o) => (
          <option key={String(o.key)} value={String(o.key)}>
            {o.label}
          </option>
        ))}
      </select>
    </Row>
  );
}

export function ColorField({ label, value, onChange, disabled }: { label: string; value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <Row label={label}>
      <span className="flex items-center gap-2">
        <input
          aria-label={label}
          className="h-8 w-10 cursor-pointer rounded border border-divider bg-transparent p-0.5"
          disabled={disabled}
          type="color"
          value={/^#[0-9a-f]{6}$/i.test(value) ? value : "#000000"}
          onChange={(e) => onChange(e.target.value)}
        />
        <span className="font-mono text-xs text-default-500">{value}</span>
      </span>
    </Row>
  );
}

export function ToggleButton({ active, onPress, label, children, disabled }: { active?: boolean; onPress: () => void; label: string; children: ReactNode; disabled?: boolean }) {
  return (
    <button
      aria-label={label}
      aria-pressed={active}
      className={clsx(
        "inline-flex h-8 min-w-8 items-center justify-center rounded-lg px-2 text-sm transition-colors disabled:opacity-40",
        active ? "bg-primary/15 text-brand-text" : "text-default-600 hover:bg-content2",
      )}
      disabled={disabled}
      title={label}
      type="button"
      // keep the caret of the inline editor
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPress}
    >
      {children}
    </button>
  );
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);

  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);

    return () => clearTimeout(t);
  }, [value, ms]);

  return v;
}
