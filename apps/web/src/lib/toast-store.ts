// The toast store (no imports, so it is unit-tested); rendered by components/Toaster.tsx.
// notify() = success, notifyError() = error. Max 3 visible; the oldest leaves when a 4th arrives.

export type ToastKind = "success" | "error";
export type Toast = { id: number; kind: ToastKind; title: string };

/** Auto-dismiss: 4.5 s, errors stay 7 s (people need time to read what went wrong). */
export const TOAST_MS: Record<ToastKind, number> = { success: 4500, error: 7000 };
export const MAX_TOASTS = 3;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit(next: Toast[]) {
  toasts = next;
  listeners.forEach((l) => l());
}

export function subscribeToasts(listener: () => void) {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
}

export const getToasts = () => toasts;
export const getServerToasts = (): Toast[] => [];

export function dismissToast(id: number) {
  emit(toasts.filter((t) => t.id !== id));
}

export function pushToast(kind: ToastKind, title: string) {
  emit([...toasts, { id: nextId++, kind, title }].slice(-MAX_TOASTS));
}

export function notify(title: string) {
  pushToast("success", title);
}
