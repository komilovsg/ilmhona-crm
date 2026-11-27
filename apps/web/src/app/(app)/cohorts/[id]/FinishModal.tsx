"use client";

import { useEffect } from "react";
import { Button } from "@heroui/button";
import { useQuery } from "@tanstack/react-query";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { ErrorState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { useRefreshEducation } from "@/hooks/education";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, isApiError, messageOf } from "@/lib/api";
import { formatPrice } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { CohortRow, FinishItem, FinishPreview } from "@/lib/types";

type Status = { status: string };

/** The finish / reopen of a cohort is a change of its status: the same version check and the same
 * «Запись уже изменили» dialog as every edit form. */
function useStatusChange(
  cohort: CohortRow,
  to: string,
  path: string,
  body: () => unknown,
  done: (result: unknown) => string,
  onClose: () => void,
) {
  const refresh = useRefreshEducation();

  return useVersionedSave<CohortRow, Status>({
    record: cohort,
    values: { status: to },
    toValues: (r) => ({ status: r.status }),
    apply: () => undefined,
    request: (_, version) => api(`/api/v1/cohorts/${cohort.id}/${path}`, { method: "POST", body: body(), version }),
    labels: { status: "Статус" },
    onSaved: (result) => {
      void refresh();
      notify(done(result));
      onClose();
    },
  });
}

function Names({ title, items, tone }: { title: string; items: FinishItem[]; tone: string }) {
  return (
    <div>
      <div className={`mb-1 text-sm font-medium ${tone}`}>
        {title}: {items.length}
      </div>
      {items.length > 0 && (
        <ul aria-label={title} className="max-h-32 space-y-0.5 overflow-auto text-sm text-default-600">
          {items.map((i) => (
            <li key={i.enrollment_id}>{i.student_name}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function FinishModal({ cohort, onClose }: { cohort: CohortRow; onClose: () => void }) {
  const preview = useQuery({
    queryKey: ["finish-preview", cohort.id],
    queryFn: () => api<FinishPreview>(`/api/v1/cohorts/${cohort.id}/finish-preview`),
    gcTime: 0,
    staleTime: 0,
  });
  const data = preview.data;
  const save = useStatusChange(
    cohort,
    "завершён",
    "finish",
    () => ({ graduates: data?.graduates, completed: data?.completed }),
    () => "Поток завершён",
    onClose,
  );
  const submit = useSubmit(() => save.save({ status: "завершён" }), !data);
  const changed = isApiError(save.failure) && save.failure.code === "finish_changed";

  useEffect(() => {
    // the numbers moved since they were shown: load them again, the user confirms the new ones
    if (changed) void preview.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [save.failure]);

  return (
    <>
      <AppModal
        footer={
          <>
            <Button variant="light" onPress={onClose}>
              Отмена
            </Button>
            <LoadingButton color="primary" isDisabled={!data} isLoading={save.pending} onPress={() => submit()}>
              Завершить поток
            </LoadingButton>
          </>
        }
        guard={false}
        isOpen
        size="md"
        title={`Завершить поток ${cohort.code}`}
        onClose={onClose}
      >
        {data ? (
          <div className="space-y-4">
            <p className="text-sm text-default-600">
              {data.overdue
                ? "Срок потока вышел."
                : "Срок потока ещё не вышел: он завершится досрочно."}{" "}
              Активные студенты закроются по проходному баллу, это можно вернуть только через суперадмина.
            </p>
            <p className="text-sm text-default-600" data-testid="lessons-to-free">
              Будет освобождено уроков: <b className="tabular-nums">{data.lessons_to_free}</b>
              {data.lessons_to_free > 0 ? " — аудитория и инструктор освободятся." : "."}
            </p>
            {!!data.debtors && (
              <p className="rounded-xl bg-warning/10 p-3 text-sm text-default-700" data-testid="finish-debt">
                Должники: <b className="tabular-nums">{data.debtors}</b> на сумму{" "}
                <b className="tabular-nums">{formatPrice(data.debt ?? 0)}</b> — долг останется в разделе «Должники».
              </p>
            )}
            <div className="grid grid-cols-3 gap-3 text-center" aria-label="Итог завершения">
              <div className="rounded-xl bg-success/10 p-3">
                <div className="font-display text-2xl font-bold tabular-nums">{data.graduates}</div>
                <div className="text-xs text-default-600">выпускников</div>
              </div>
              <div className="rounded-xl bg-default-100 p-3">
                <div className="font-display text-2xl font-bold tabular-nums">{data.completed}</div>
                <div className="text-xs text-default-600">завершат</div>
              </div>
              <div className="rounded-xl bg-default-100 p-3">
                <div className="font-display text-2xl font-bold tabular-nums">{data.excluded_count}</div>
                <div className="text-xs text-default-600">не затронуты</div>
              </div>
            </div>
            <div className="space-y-3">
              <Names items={data.lists.graduates} title="Станут выпускниками" tone="text-success-700 dark:text-success" />
              <Names items={data.lists.completed} title="Получат статус «завершил»" tone="" />
              {data.lists.excluded.length > 0 && (
                <div>
                  <div className="mb-1 text-sm font-medium text-default-500">
                    Не затронуты: {data.lists.excluded.length}
                  </div>
                  <ul aria-label="Не затронуты" className="max-h-32 space-y-0.5 overflow-auto text-sm text-default-500">
                    {data.lists.excluded.map((i) => (
                      <li key={i.enrollment_id}>
                        {i.student_name} — {i.status}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            {save.failure !== null && (
              <p className="text-sm text-danger" role="alert">
                {messageOf(save.failure)}
              </p>
            )}
          </div>
        ) : preview.isError ? (
          <ErrorState retrying={preview.isFetching} text="Не удалось посчитать" onRetry={() => void preview.refetch()} />
        ) : (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Bone key={i} className="h-6 w-full" />
            ))}
          </div>
        )}
      </AppModal>
      <ConflictDialog save={save} />
    </>
  );
}

/** The reopen answer lists the lessons whose slot was taken meanwhile: they stay cancelled. */
function reopenText(result: unknown): string {
  const busy = (result as { lessons_busy?: { date: string; start: string; end: string; room_name: string }[] } | null)
    ?.lessons_busy;

  if (!busy?.length) return "Поток возвращён в активные";
  const shown = busy
    .slice(0, 5)
    .map((l) => `${l.date.slice(8, 10)}.${l.date.slice(5, 7)} ${l.start}–${l.end}`)
    .join(", ");

  return `Поток возвращён. Уроки не возвращены, аудитория занята (${busy.length}): ${shown}${busy.length > 5 ? " …" : ""}`;
}

export function ReopenModal({ cohort, onClose }: { cohort: CohortRow; onClose: () => void }) {
  const save = useStatusChange(cohort, "активный", "reopen", () => undefined, reopenText, onClose);
  const submit = useSubmit(() => save.save({ status: "активный" }));

  return (
    <>
      <AppModal
        footer={
          <>
            <Button variant="light" onPress={onClose}>
              Отмена
            </Button>
            <LoadingButton color="primary" isLoading={save.pending} onPress={() => submit()}>
              Вернуть в активные
            </LoadingButton>
          </>
        }
        guard={false}
        isOpen
        size="md"
        title={`Вернуть поток ${cohort.code}`}
        onClose={onClose}
      >
        <div className="space-y-3 text-sm text-default-600">
          <p>
            Поток снова станет «активным», студенты вернутся к статусам, которые были до завершения, а отменённые при
            завершении уроки вернутся в расписание. Если время уже занято другим потоком, такой урок останется
            отменённым.
          </p>
          {save.failure !== null && (
            <p className="text-danger" role="alert">
              {messageOf(save.failure)}
            </p>
          )}
        </div>
      </AppModal>
      <ConflictDialog save={save} />
    </>
  );
}
