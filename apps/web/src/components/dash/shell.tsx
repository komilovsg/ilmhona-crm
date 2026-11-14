"use client";

import type { CSSProperties, ReactNode } from "react";
import clsx from "clsx";
import { motion } from "framer-motion";
import Link from "next/link";

import { Bone } from "@/components/Skeletons";
import { useReducedMotion } from "@/lib/client-store";
import { EASE_OUT } from "@/lib/motion";

/** Staggered rise of a card: opacity and 10 px of translate only, nothing under reduced motion. */
export function DashCard({
  title,
  aside,
  children,
  className,
  delay = 0,
  hero,
  label,
}: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  delay?: number;
  hero?: boolean;
  label?: string;
}) {
  const reduced = useReducedMotion();

  return (
    <motion.section
      aria-label={title ?? label}
      className={clsx("flex min-w-0 flex-col gap-4 rounded-2xl bg-content1 p-4 md:p-6", hero && "md:p-8", className)}
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduced ? 0 : 0.5, ease: EASE_OUT, delay: reduced ? 0 : delay }}
    >
      {(title || aside) && (
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          {title && <h2 className="font-display text-lg font-semibold leading-7 md:text-xl">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </motion.section>
  );
}

/** A bar that grows from 0 along x (transform only). */
export function GrowX({ className, style, delay = 0 }: { className?: string; style?: CSSProperties; delay?: number }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      aria-hidden="true"
      className={className}
      initial={reduced ? false : { scaleX: 0 }}
      animate={{ scaleX: 1 }}
      style={{ originX: 0, ...style }}
      transition={{ duration: reduced ? 0 : 0.9, ease: EASE_OUT, delay: reduced ? 0 : delay }}
    />
  );
}

/** A column that grows from the baseline (transform only). */
export function GrowY({ className, style, delay = 0 }: { className?: string; style?: CSSProperties; delay?: number }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      aria-hidden="true"
      className={className}
      initial={reduced ? false : { scaleY: 0 }}
      animate={{ scaleY: 1 }}
      style={{ originY: 1, ...style }}
      transition={{ duration: reduced ? 0 : 0.8, ease: EASE_OUT, delay: reduced ? 0 : delay }}
    />
  );
}

/** The «today» line: a slow pulse, still under reduced motion. */
export function PulseLine({ left }: { left: number }) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      aria-hidden="true"
      className="absolute inset-y-0 w-0.5 rounded-sm"
      animate={reduced ? { opacity: 1 } : { opacity: [0.35, 1, 0.35] }}
      style={{ left: `${left}%`, background: "var(--chart-accent)" }}
      transition={reduced ? { duration: 0 } : { duration: 2.4, ease: "easeInOut", repeat: Infinity }}
    />
  );
}

/** «График / Таблица»: every chart can be read as a table. */
export function ViewToggle({ table, onChange }: { table: boolean; onChange: (table: boolean) => void }) {
  const option = (on: boolean, text: string) => (
    <button
      aria-pressed={table === on}
      className={clsx(
        "h-8 rounded-md px-3 text-xs font-medium transition-colors",
        table === on ? "bg-content1 text-foreground shadow-sm" : "text-default-500 hover:text-foreground",
      )}
      type="button"
      onClick={() => onChange(on)}
    >
      {text}
    </button>
  );

  return (
    <div aria-label="Вид" className="inline-flex gap-0.5 rounded-lg bg-content2 p-0.5" role="group">
      {option(false, "График")}
      {option(true, "Таблица")}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color?: string; line?: boolean; outline?: boolean }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-default-500">
      {items.map((i) => (
        <li key={i.label} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={clsx(i.line ? "h-3 w-0.5" : "size-2.5 rounded-[3px]", i.outline && "border border-default-400")}
            style={{ background: i.color }}
          />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** The card's skeleton: the title line and `rows` rows of `rowClass` height (the real rows' size). */
export function CardSkeleton({ rows = 4, rowClass = "h-12", className }: { rows?: number; rowClass?: string; className?: string }) {
  return (
    <div className={clsx("flex flex-col gap-4", className)}>
      {Array.from({ length: rows }, (_, i) => (
        <Bone key={i} className={clsx("w-full rounded-xl", rowClass)} />
      ))}
    </div>
  );
}

export function RowLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link
      className={clsx("block min-w-0 rounded-xl bg-content2 px-3.5 py-3 transition-colors hover:bg-default-200 focus-visible:outline-2", className)}
      href={href}
    >
      {children}
    </Link>
  );
}

export const TONE_TEXT = {
  up: "text-success-600 dark:text-success",
  down: "text-danger",
  flat: "text-default-500",
  new: "text-default-500",
} as const;

export const nbsp = (s: string) => s.replace(/ /g, " ");
