import clsx from "clsx";

// Shape-matched placeholders. Each one copies the box model of the real content (same paddings,
// same line heights, same grid), so when the data arrives nothing moves (CLS stays ~0).
// Server-safe: used by loading.tsx too.

export function Bone({ className }: { className?: string }) {
  return <div aria-hidden="true" className={clsx("bone rounded-md bg-default-200", className)} />;
}

/** The skeleton is invisible for the first 300 ms (fast answers never flash it) but reserves its space. */
export function Late({ children, delay = 300 }: { children: React.ReactNode; delay?: number }) {
  return (
    <div className="appear-late" style={{ "--late": `${delay}ms` } as React.CSSProperties}>
      {children}
    </div>
  );
}

const WIDTHS = ["w-40", "w-28", "w-24", "w-32", "w-20", "w-16"];

/** Desktop table: header row (text-xs, py-3) and body rows (text-sm, py-3), like the real ones. */
export function TableSkeleton({ cols = 5, rows = 8 }: { cols?: number; rows?: number }) {
  return (
    <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-divider text-xs text-default-500">
          <tr>
            {Array.from({ length: cols }, (_, c) => (
              <th key={c} className="px-4 py-3 font-medium">
                <Bone className={clsx("h-4", WIDTHS[(c + 2) % WIDTHS.length])} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, r) => (
            <tr key={r} className="border-b border-divider last:border-0">
              {Array.from({ length: cols }, (_, c) => (
                <td key={c} className="px-4 py-3">
                  <Bone className={clsx("h-5", WIDTHS[(r + c) % WIDTHS.length])} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Phone card: title line, sub line, meta line (p-4, like the real `li`). */
export function CardRowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <ul className="space-y-3 md:hidden">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className="rounded-2xl bg-content1 p-4">
          <Bone className="h-6 w-2/3" />
          <Bone className="mt-1 h-5 w-1/3" />
          <Bone className="mt-2 h-5 w-1/2" />
        </li>
      ))}
    </ul>
  );
}

/** A table on desktop, cards on a phone: what every list page shows. */
export function ListSkeleton({ cols = 5, rows = 8 }: { cols?: number; rows?: number }) {
  return (
    <>
      <TableSkeleton cols={cols} rows={rows} />
      <CardRowsSkeleton rows={Math.min(rows, 6)} />
    </>
  );
}

/** Cohort cards grid (same grid classes as the cohorts page). */
export function CardGridSkeleton({ cards = 6, lines = 4 }: { cards?: number; lines?: number }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="flex flex-col gap-3 rounded-2xl bg-content1 p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <Bone className="h-4 w-16" />
              <Bone className="mt-1 h-6 w-2/3" />
            </div>
            <Bone className="h-6 w-16 rounded-full" />
          </div>
          <div className="grid gap-1.5">
            {Array.from({ length: lines }, (_, k) => (
              <Bone key={k} className="h-5 w-3/4" />
            ))}
          </div>
          <div>
            <Bone className="mb-1 h-4 w-full" />
            <Bone className="h-2 w-full rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Row of count pills above a list (h-7 pills, mb-4). */
export function PillsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div aria-hidden="true" className="mb-4 flex flex-wrap gap-2">
      {Array.from({ length: count }, (_, i) => (
        <Bone key={i} className="h-7 w-24 rounded-full" />
      ))}
    </div>
  );
}

/** Page title row (text-2xl, mb-5) and optional action button. */
export function HeaderSkeleton({ action = false }: { action?: boolean }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div className="flex h-8 items-center">
        <Bone className="h-7 w-48" />
      </div>
      {action && <Bone className="h-10 w-28 rounded-xl" />}
    </div>
  );
}

/** Detail page head: back link, title + subtitle, then the info card (grid like cohort detail). */
export function DetailSkeleton({ cells = 6, withTable = true }: { cells?: number; withTable?: boolean }) {
  return (
    <>
      <div className="mb-3 flex h-5 items-center">
        <Bone className="h-4 w-20" />
      </div>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex h-8 items-center">
            <Bone className="h-7 w-44" />
          </div>
          <div className="mt-1 flex h-6 items-center">
            <Bone className="h-5 w-64 max-w-full" />
          </div>
        </div>
        <Bone className="h-8 w-8 rounded-lg" />
      </div>
      {cells > 0 && (
        <section className="mb-5 grid gap-4 rounded-2xl bg-content1 p-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: cells }, (_, i) => (
            <div key={i} className="flex items-start gap-3">
              <Bone className="mt-0.5 h-8 w-8 rounded-lg" />
              <div className="min-w-0 flex-1">
                <Bone className="h-4 w-16" />
                <Bone className="mt-1 h-5 w-32" />
              </div>
            </div>
          ))}
        </section>
      )}
      {withTable && (
        <>
          <Bone className="mb-4 h-10 w-56 rounded-xl" />
          <ListSkeleton cols={4} rows={5} />
        </>
      )}
    </>
  );
}

/** A form: label + field (h-14 like HeroUI inputs), repeated. */
export function FormSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <div className="max-w-xl space-y-4 rounded-2xl bg-content1 p-4 md:p-6">
      {Array.from({ length: fields }, (_, i) => (
        <Bone key={i} className="h-14 w-full rounded-xl" />
      ))}
      <Bone className="h-10 w-32 rounded-xl" />
    </div>
  );
}

/** Whole page: header + toolbar + list. Used by loading.tsx of the list routes. */
export function ListPageSkeleton({
  action = true,
  cols = 5,
  cards = false,
  cardLines,
}: {
  action?: boolean;
  cols?: number;
  cards?: boolean;
  cardLines?: number;
}) {
  return (
    <Late>
      <HeaderSkeleton action={action} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Bone className="h-10 flex-1 rounded-xl md:max-w-xs md:flex-none md:basis-80" />
        <Bone className="hidden h-14 w-44 rounded-xl md:block" />
      </div>
      {cards ? <CardGridSkeleton lines={cardLines} /> : <ListSkeleton cols={cols} />}
    </Late>
  );
}
