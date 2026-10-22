"use client";

import { useState } from "react";

import { isApiError, messageOf } from "@/lib/api";
import { errorText } from "@/lib/api-errors";

/**
 * Field hints of a rejected form (422): `const fe = useFieldErrors(mutation.error, ["full_name", "phone"])`
 * (the list = the API fields that have an input), then `<Input {...fe.field("phone", setPhone)} />`
 * (or `{...fe.hint("phone")}` + `fe.clear("phone")` for other inputs). A hint goes away when the
 * user edits its field and on the next submit (a new error). `fe.message` is the text for the
 * dialog: null when there is no error or every rejected field shows its hint.
 */
export function useFieldErrors(error: unknown, fields: string[]) {
  const [cleared, setCleared] = useState<{ error: unknown; names: string[] }>({ error: null, names: [] });
  const gone = cleared.error === error ? cleared.names : [];
  const all = isApiError(error) && error.status === 422 ? (error.fieldErrors ?? {}) : {};
  const rejected = Object.keys(all);
  const shown = rejected.filter((k) => fields.includes(k) && !gone.includes(k));
  const everyOnScreen = rejected.length > 0 && rejected.every((k) => fields.includes(k));

  const clear = (name: string) => {
    if (error && !gone.includes(name)) setCleared({ error, names: [...gone, name] });
  };
  const hint = (name: string) => ({
    isInvalid: shown.includes(name),
    errorMessage: shown.includes(name) ? all[name] : undefined,
  });

  return {
    hint,
    clear,
    /** Props for an input whose change handler takes the new string value. */
    field: (name: string, set: (value: string) => void) => ({
      ...hint(name),
      onValueChange: (value: string) => {
        clear(name);
        set(value);
      },
    }),
    message: !error
      ? null
      : everyOnScreen
        ? shown.length
          ? errorText("check_marked_fields")
          : null
        : messageOf(error),
  };
}
