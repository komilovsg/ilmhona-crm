"use client";

import { useState } from "react";

import { LoadingButton } from "@/components/LoadingButton";
import { useRefreshEducation } from "@/hooks/education";
import { api, messageOf } from "@/lib/api";
import { overToast } from "@/lib/capacity";
import type { JournalPreview, UnmatchedName } from "@/lib/journal-import";
import { notify, notifyError } from "@/lib/toast";
import type { Fill } from "@/lib/types";

type Enrolled = { over_capacity: Fill | null };
type Body = { student_id: string } | { new_student: { full_name: string } };

const TIER: Record<string, string> = { exact: "точное совпадение", translit: "та же запись", tokens: "похожее имя", similar: "возможно" };

/** The names of the file that are not in the group: write each into it (an existing student of the
 * branch or a new one), or all the single exact matches at once. The preview is rebuilt after each. */
export function JournalUnmatched({
  cohortId,
  rows,
  canEnroll,
  onChanged,
}: {
  cohortId: string;
  rows: JournalPreview["unmatched"];
  canEnroll: boolean;
  onChanged: () => void;
}) {
  const refresh = useRefreshEducation();
  const [busy, setBusy] = useState<string | null>(null);
  const url = `/api/v1/cohorts/${cohortId}/attendance/import/enroll`;

  const enrollOne = async (u: UnmatchedName, body: Body): Promise<Fill | null> => {
    const row = await api<Enrolled>(url, { method: "POST", body: { ...body, first_date: u.first_date } });

    return row.over_capacity;
  };
  const done = (over: Fill | null, text: string) => {
    void refresh();
    notify(`${text}${overToast(over)}`);
    onChanged();
  };

  const one = async (u: UnmatchedName, key: string, body: Body) => {
    if (busy) return;
    setBusy(key);
    try {
      done(await enrollOne(u, body), "Студент записан в поток");
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(null);
    }
  };

  const exact = rows.filter((u) => u.options.length === 1 && u.options[0].tier === "exact");
  const all = async () => {
    if (busy) return;
    setBusy("all");
    let n = 0;
    let over: Fill | null = null;

    try {
      for (const u of exact) {
        over = (await enrollOne(u, { student_id: u.options[0].student_id })) ?? over;
        n += 1;
      }
    } catch (e) {
      notify(`Записано: ${n}. ${messageOf(e)}`);
    } finally {
      setBusy(null);
      if (n > 0) done(over, `Записано студентов: ${n}`);
    }
  };

  return (
    <section aria-label={`Нет в группе: ${rows.length}`}>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Нет в группе: {rows.length}</h3>
        {canEnroll && exact.length > 1 && (
          <LoadingButton color="primary" isLoading={busy === "all"} size="sm" variant="flat" onPress={() => void all()}>
            Записать всех ({exact.length})
          </LoadingButton>
        )}
      </div>
      {!canEnroll && (
        <p className="mb-1.5 rounded-xl bg-warning-50 p-3 text-sm text-warning-700 dark:bg-warning/10 dark:text-warning" role="status">
          Этих студентов нет в группе: попросите менеджера записать их, тогда их отметки загрузятся.
        </p>
      )}
      <ul className="divide-y divide-divider rounded-xl border border-divider text-sm">
        {rows.map((u) => (
          <li key={u.line} className="space-y-2 px-3 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={u.struck ? "line-through" : "font-medium"}>{u.name}</span>
              <span className="text-xs text-default-500">
                {u.struck && "вычеркнут · "}отметок: {u.marks}
              </span>
            </div>
            {canEnroll && (
              <div className="flex flex-wrap gap-2">
                {u.options.map((o) => (
                  <LoadingButton
                    key={o.student_id}
                    color="primary"
                    isDisabled={!!busy}
                    isLoading={busy === `${u.line}:${o.student_id}`}
                    size="sm"
                    variant="flat"
                    onPress={() => void one(u, `${u.line}:${o.student_id}`, { student_id: o.student_id })}
                  >
                    Записать: {o.student_name}
                    {o.phone ? ` · ${o.phone}` : ""} ({TIER[o.tier] ?? o.tier})
                  </LoadingButton>
                ))}
                <LoadingButton
                  isDisabled={!!busy}
                  isLoading={busy === `${u.line}:new`}
                  size="sm"
                  variant="bordered"
                  onPress={() => void one(u, `${u.line}:new`, { new_student: { full_name: u.name } })}
                >
                  Создать и записать
                </LoadingButton>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
