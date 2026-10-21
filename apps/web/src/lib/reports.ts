// Pure helpers of the report screens (no React: unit-tested with node --test).

const SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

/** The chart tick for a month: «окт» from `2026-10-01`. */
export function shortMonth(iso: string): string {
  return SHORT[Number(iso.slice(5, 7)) - 1] ?? iso.slice(5, 7);
}

/** Compact money for chart axes: 1 250 000 -> «1,3 млн», 12 500 -> «12,5 тыс.». */
export function compact(value: number): string {
  const abs = Math.abs(value);
  const fmt = (n: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(n);

  if (abs >= 1_000_000) return `${fmt(value / 1_000_000)} млн`;
  if (abs >= 1_000) return `${fmt(value / 1_000)} тыс.`;

  return fmt(value);
}

/** «—» for a number the API could not compute (a zero divisor), never a fake 0. */
export function orDash(value: string | null | undefined, format: (v: string) => string): string {
  return value == null ? "—" : format(value);
}

/** Round axis ticks covering [min, max] and 0: about `count` steps. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  const lo = Math.min(0, min);
  const hi = Math.max(0, max) || (lo === 0 ? 4 : 0); // an all-zero chart still gets an axis
  const raw = (hi - lo || 1) / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];

  for (let t = Math.floor(lo / step) * step; t < hi + step - 1e-9; t += step) {
    ticks.push(Math.round(t * 100) / 100);
    if (t >= hi) break;
  }

  return ticks;
}

export const FORMAT_LABEL: Record<string, string> = { offline: "Офлайн", online: "Онлайн" };
