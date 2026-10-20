import { addToast } from "@heroui/toast";

import { messageOf } from "./api";

export function notify(title: string) {
  addToast({ title, color: "success", timeout: 3000 });
}

export function notifyError(error: unknown) {
  addToast({ title: messageOf(error), color: "danger", timeout: 6000 });
}
