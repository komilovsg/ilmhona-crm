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
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { CohortRow, FinishItem, FinishPreview } from "@/lib/types";

type Status = { status: string };

/** The finish / reopen of a cohort is a change of its status: the same version check and the same
 * «Запись уже изменили» dialog as every edit form. */
function useStatusChange(cohort: CohortRow, to: string, path: string, body: () => unknown, done: string, onClose: () => void) {
  const refresh = useRefreshEducation();

  return useVersionedSave<CohortRow, Status>({
    record: cohort,
    values: { status: to },
    toValues: (r) => ({ status: r.status }),
    apply: () => undefined,
    request: (_, version) => api(`/api/v1/cohorts/${cohort.id}/${path}`, { method: "POST", body: body(), version }),
    labels: { status: "Статус" },
    onSaved: () => {
      void refresh();
      notify(done);
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
    "Поток завершён",
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

export function ReopenModal({ cohort, onClose }: { cohort: CohortRow; onClose: () => void }) {
  const save = useStatusChange(cohort, "активный", "reopen", () => undefined, "Поток возвращён в активные", onClose);
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
          <p>Поток снова станет «активным», а студенты вернутся к статусам, которые были до завершения.</p>
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
