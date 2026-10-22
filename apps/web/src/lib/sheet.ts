// Pure logic of the swipe gestures (bottom sheets and phone toasts). No DOM here, so it is unit-tested.
// Numbers follow apple-design: dismiss by projected travel or by flick velocity (not by position alone),
// resistance that grows past a boundary (rubber-band), a ~10 px hysteresis before a drag is claimed.

/** Movement (px) before a touch counts as a drag and its direction is decided. */
export const DRAG_SLOP = 10;
/** A downward flick at least this fast (px/s) closes a sheet, an upward one keeps it open. */
export const FLICK_VELOCITY = 600;
/** A sheet released past this share of its height closes without a flick. */
export const CLOSE_RATIO = 0.35;

/** Soft boundary: the further past the edge, the less the thing follows (apple-design §9). */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  const o = Math.abs(overshoot);

  return (o * dimension * constant) / (dimension + constant * o);
}

/** Where the sheet sits for a raw finger offset: 1:1 downwards, rubber-banded upwards (past fully open). */
export function sheetOffset(raw: number, height: number): number {
  return raw >= 0 ? raw : -rubberband(raw, Math.min(height, 160));
}

/** Release of a sheet: close on a fast downward flick or when dragged far enough; a flick up cancels. */
export function shouldCloseSheet({ offset, velocity, height }: { offset: number; velocity: number; height: number }): boolean {
  if (offset <= 0) return false;
  if (velocity <= -FLICK_VELOCITY / 2) return false;
  if (velocity >= FLICK_VELOCITY && offset >= 24) return true;

  return offset >= height * CLOSE_RATIO;
}

export type SwipeDir = "up" | "left" | "right";

/** Release of a phone toast: swipe up or sideways far enough or fast enough. Down and taps never dismiss. */
export function toastSwipe({ dx, dy, vx, vy }: { dx: number; dy: number; vx: number; vy: number }): SwipeDir | null {
  const up = dy < -36 || (vy < -500 && dy < -8);
  const side = Math.abs(dx) > 96 || (Math.abs(vx) > 600 && Math.abs(dx) > 16);

  if (side && (!up || Math.abs(dx) >= Math.abs(dy))) return dx < 0 ? "left" : "right";
  if (up) return "up";

  return null;
}

export type Sample = { y: number; t: number };

/** Release velocity (px/s) from the last ~100 ms of pointer samples (a short history, not the last two points). */
export function velocityOf(samples: Sample[], window = 100): number {
  const last = samples[samples.length - 1];

  if (!last) return 0;
  const first = samples.find((s) => last.t - s.t < window) ?? last;

  return last.t === first.t ? 0 : ((last.y - first.y) / (last.t - first.t)) * 1000;
}

/**
 * The user tries to dismiss a dialog (Esc, backdrop, swipe): close at once, or ask first when a form was
 * edited. The one rule for every form.
 */
export function dismissAction({ dirty, guarded = true }: { dirty: boolean; guarded?: boolean }): "close" | "confirm" {
  return dirty && guarded ? "confirm" : "close";
}

/** Fields whose events mean the user edited the form (not buttons, not a search box). */
export function isEditField(el: { tagName?: string; type?: string; readOnly?: boolean } | null): boolean {
  if (!el?.tagName) return false;
  const tag = el.tagName.toUpperCase();

  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag !== "INPUT") return false;

  return !el.readOnly && !["button", "submit", "reset", "search"].includes(el.type ?? "text");
}
