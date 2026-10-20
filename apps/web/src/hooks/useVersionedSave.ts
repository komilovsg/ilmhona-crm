"use client";

import { useRef, useState } from "react";

import { messageOf } from "@/lib/api";
import {
  changedKeys,
  conflictLines,
  rebase,
  staleOf,
  whoWhen,
  type ConflictLine,
  type StaleInfo,
  type Values,
} from "@/lib/conflict";

type Options<R extends { version: number }, V extends Values> = {
  /** The record the form was opened on (with its `version`); null while creating. */
  record: R | null;
  /** The form's current fields as one object (keys = what the user can change). */
  values: V;
  /** Record -> form fields. */
  toValues: (record: R) => V;
  /** Put fields back into the form (after «Обновить и повторить»). */
  apply: (values: V) => void;
  /** The PATCH: `changed` has only the fields the user changed; `version` goes to `If-Match`. */
  request: (changed: Partial<V>, version: number, all: V) => Promise<unknown>;
  /** Field names for the conflict dialog, and optional value formatters. */
  labels: Partial<Record<keyof V, string>>;
  show?: Partial<Record<keyof V, (value: never) => string>>;
  onSaved: (result: unknown) => void;
};

export type Conflict = { title: string; lines: ConflictLine[] };

/**
 * The one save for every edit form (#25). Sends only the changed fields with the version the
 * form loaded. On 409 it keeps the form open and offers `retry` (reload the record, put the
 * user's changed fields on top of it, send again) or `cancel`. The dialog is `<ConflictDialog>`.
 */
export function useVersionedSave<R extends { version: number }, V extends Values>(opts: Options<R, V>) {
  const latest = useRef(opts);
  const [base, setBase] = useState<R | null>(opts.record);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState<{ info: StaleInfo<R>; mine: V } | null>(null);

  // read at call time only (a submit), never during render
  // eslint-disable-next-line react-hooks/refs
  latest.current = opts;

  async function run(baseRecord: R, values: V) {
    const { toValues, request, onSaved } = latest.current;
    const before = toValues(baseRecord);
    const keys = changedKeys(before, values);

    setPending(true);
    setError(null);
    try {
      const changed = Object.fromEntries(keys.map((k) => [k, values[k]])) as Partial<V>;

      const result = keys.length ? await request(changed, baseRecord.version, values) : null;

      // the answer is the record as saved: the next save of an open form starts from its version
      if (result && typeof result === "object" && "version" in result) setBase(result as R);
      onSaved(result);
    } catch (e) {
      const info = staleOf<R>(e);

      if (info) setStale({ info, mine: values });
      else setError(messageOf(e));
    } finally {
      setPending(false);
    }
  }

  /** «Обновить и повторить»: the fresh record becomes the base, my changed fields go on top. */
  async function retry() {
    if (!stale || !base) return;
    const { toValues, apply } = latest.current;
    const merged = rebase(toValues(base), toValues(stale.info.current), stale.mine);

    setStale(null);
    setBase(stale.info.current);
    apply(merged);
    await run(stale.info.current, merged);
  }

  let conflict: Conflict | null = null;

  if (stale && base) {
    const { toValues, labels, show } = opts;
    const keys = changedKeys(toValues(base), stale.mine);

    conflict = {
      title: whoWhen(stale.info),
      lines: conflictLines(keys, stale.mine, toValues(stale.info.current), labels, show),
    };
  }

  return {
    /** Send the form's current `values` (the caller passes them: they live in its state). */
    save: async (values: V) => {
      if (base) await run(base, values);
    },
    pending,
    error,
    conflict,
    retry,
    cancel: () => setStale(null),
  };
}

export type VersionedSave = ReturnType<typeof useVersionedSave>;
