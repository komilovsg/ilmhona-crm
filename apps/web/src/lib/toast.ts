// The one toast system: notify() = success, notifyError() = error (store in toast-store.ts, view in
// components/Toaster.tsx). Max 3 visible; the oldest leaves when a 4th arrives.

import { messageOf } from "./api";
import { pushToast } from "./toast-store";

export { notify } from "./toast-store";

export function notifyError(error: unknown) {
  pushToast("error", messageOf(error));
}
