import type { Fill } from "./types.ts";

/** Capacity is a soft limit: staff are never blocked, but going over the plan is shown and confirmed. */

/** Seats over the plan right now (0 when within it). */
export function overBy(fill: Fill): number {
  return Math.max(fill.enrolled - fill.capacity, 0);
}

/** One more enrollment would go over the plan. */
export function wouldExceed(fill: Fill | undefined): boolean {
  return !!fill && fill.enrolled + 1 > fill.capacity;
}

export function overWarning(fill: Fill): string {
  return `Сверх плана: будет ${fill.enrolled + 1} из ${fill.capacity}. Записать всё равно?`;
}

/** Toast tail for a save whose response carries `over_capacity`. */
export function overToast(over: Fill | null | undefined): string {
  return over ? `, сверх плана: ${over.enrolled} из ${over.capacity}` : "";
}
