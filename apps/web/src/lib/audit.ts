// The audit page helpers (no React, no imports: unit-tested with node --test). The sentences
// themselves are written by the API (app/audit/sentences.py); the web only groups and links them.

export type AuditLink = { entity: string; id: string };

const TZ = "Asia/Dushanbe";
const dayFormat = new Intl.DateTimeFormat("en-CA", { timeZone: TZ }); // 2026-10-20
const longDay = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, day: "numeric", month: "long", year: "numeric" });
const clock = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });

/** Where a log entry leads: students and cohorts have their own page, the rest a list page. */
export function linkHref(link: AuditLink | null): string | null {
  if (!link) return null;
  switch (link.entity) {
    case "student":
      return `/students/${link.id}`;
    case "cohort":
      return `/cohorts/${link.id}`;
    case "app_user":
      return "/users";
    case "role":
      return "/roles";
    case "room":
    case "course":
      return "/rooms";
    default:
      return null;
  }
}

/** `2026-10-20` in Dushanbe time. */
export function dayKey(iso: string): string {
  return dayFormat.format(new Date(iso));
}

export function timeOf(iso: string): string {
  return clock.format(new Date(iso));
}

/** «Сегодня» · «Вчера» · «18 октября 2026». */
export function dayLabel(day: string, now: Date = new Date()): string {
  if (day === dayKey(now.toISOString())) return "Сегодня";
  if (day === dayKey(new Date(now.getTime() - 86_400_000).toISOString())) return "Вчера";

  return longDay.format(new Date(`${day}T12:00:00+05:00`));
}

export type DayGroup<T> = { day: string; label: string; items: T[] };

/** Entries (newest first) grouped by calendar day, order kept. */
export function groupByDay<T extends { at: string }>(items: T[], now: Date = new Date()): DayGroup<T>[] {
  const groups: DayGroup<T>[] = [];

  for (const item of items) {
    const day = dayKey(item.at);
    const last = groups.at(-1);

    if (last?.day === day) last.items.push(item);
    else groups.push({ day, label: dayLabel(day, now), items: [item] });
  }

  return groups;
}
