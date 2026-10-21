import { messageOf } from "./api";

// @heroui/toast loads on demand (the provider in the root layout pulls the same chunk at start), so the
// toast code is not in the first-load bundle of every page.
type Toast = { title: string; color: "success" | "danger"; timeout: number };

function show(toast: Toast) {
  void import("@heroui/toast").then((m) => m.addToast(toast));
}

export function notify(title: string) {
  show({ title, color: "success", timeout: 3000 });
}

export function notifyError(error: unknown) {
  show({ title: messageOf(error), color: "danger", timeout: 6000 });
}
