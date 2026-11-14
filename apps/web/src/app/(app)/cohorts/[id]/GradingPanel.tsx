"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { AppModal } from "@/components/AppModal";
import { ConfirmModal } from "@/components/ConfirmModal";
import {
  ArchiveConfirm,
  ConflictDialog,
  ExcelActions,
  SchemeChips,
  SchemeEditor,
  notifySaved,
  useSchemeSave,
  type SchemePayload,
} from "@/components/GradingScheme";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { ErrorState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { api, isApiError, messageOf } from "@/lib/api";
import { TARGETS } from "@/lib/grading";
import { notify, notifyError } from "@/lib/toast";

type CohortScheme = SchemePayload & {
  cohort_id: string;
  cohort_code: string;
  source: "standard" | "cohort";
  archived: { key: string; name: string; scores: number }[];
  completed: boolean;
};

type Change = {
  enrollment_id: string;
  student_name: string;
  status: string;
  new_status: string;
  total: number;
  reason?: string;
};
type Recalc = { completed: boolean; changes: Change[]; skipped: Change[]; graduates: number; not_graduates: number };

function PanelSkeleton() {
  return (
    <div className="mb-4 space-y-3 rounded-2xl bg-content1 p-4">
      <Bone className="h-5 w-48" />
      <div className="flex flex-wrap gap-2">
        {[0, 1, 2].map((i) => (
          <Bone key={i} className="h-8 w-32 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

/**
 * «Шкала оценок» of one cohort: the standard of the academy or the cohort's own, edited by who
 * grades the cohort (the API decides: instructor of the cohort, a manager of the branch, the
 * superadmin), «Вернуть стандарт академии», the Excel round trip and, for a finished cohort, the
 * graduation recalculation (a scheme change never flips a status by itself).
 */
export function GradingPanel({ cohortId }: { cohortId: string }) {
  const query = useQuery({
    queryKey: ["grading", cohortId],
    queryFn: () => api<CohortScheme>(`/api/v1/cohorts/${cohortId}/grading`),
  });

  if (query.data) return <Panel key={`${query.data.source}-${query.data.version}`} data={query.data} />;
  if (query.isError)
    return (
      <div className="mb-4">
        <ErrorState retrying={query.isFetching} text="Не удалось загрузить шкалу оценок" onRetry={() => void query.refetch()} />
      </div>
    );

  return <PanelSkeleton />;
}

function Panel({ data }: { data: CohortScheme }) {
  const queryClient = useQueryClient();
  const path = `/api/v1/cohorts/${data.cohort_id}/grading`;
  const [editing, setEditing] = useState(false);
  const [resetting, setResetting] = useState<"ask" | "archive" | null>(null);
  const [resetBusy, setResetBusy] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const refresh = (result?: SchemePayload) => {
    if (result) queryClient.setQueryData(["grading", data.cohort_id], result);
    void queryClient.invalidateQueries({ queryKey: ["grading", data.cohort_id] });
    void queryClient.invalidateQueries({ queryKey: ["grades", data.cohort_id] });
  };
  const s = useSchemeSave(path, data, (result) => {
    refresh(result);
    setEditing(false);
    notifySaved();
  });

  const reset = async (confirmArchive: boolean) => {
    setResetBusy(true);
    try {
      const result = await api<SchemePayload>(`${path}${confirmArchive ? "?confirm_archive=true" : ""}`, {
        method: "DELETE",
        version: data.version,
      });

      setResetting(null);
      refresh(result);
      notify("Вернули стандарт академии");
    } catch (e) {
      if (isApiError(e) && e.code === "grading_scores_archived") setResetting("archive");
      else {
        setResetting(null);
        notifyError(e);
        refresh();
      }
    } finally {
      setResetBusy(false);
    }
  };

  const own = data.source === "cohort";

  return (
    <section aria-label="Шкала оценок" className="mb-4 space-y-3 rounded-2xl bg-content1 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">Шкала оценок</h2>
          <span
            className={clsx(
              "rounded-md px-2 py-0.5 text-xs font-medium",
              own ? "bg-warning/15 text-warning-700 dark:text-warning" : "bg-primary/10 text-brand-text",
            )}
          >
            {own ? "своя для потока" : "стандарт академии"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ExcelActions
            canImport={data.can_edit}
            importPath={`${path}/import`}
            templatePath={`${path}/template`}
            onApply={(values) => s.run(values)}
          />
          {data.can_edit && (
            <Button size="md" startContent={<Icon name="edit" size={18} />} variant="flat" onPress={() => setEditing(true)}>
              Изменить
            </Button>
          )}
          {data.can_edit && own && (
            <Button size="md" variant="light" onPress={() => setResetting("ask")}>
              Вернуть стандарт академии
            </Button>
          )}
          {data.completed && data.can_edit && (
            <Button size="md" startContent={<Icon name="graduates" size={18} />} variant="flat" onPress={() => setRecalc(true)}>
              Пересчитать выпускников
            </Button>
          )}
        </div>
      </div>
      <SchemeChips scheme={data.scheme} />
      <p className="text-xs text-default-500">
        {TARGETS.map((t) => `${t.label.replace(", %", "")}: ${data.scheme[t.key]}${t.key === "pass_score" ? "" : " %"}`).join(" · ")}
      </p>
      {data.archived.length > 0 && (
        <p className="text-xs text-default-500">
          В архиве (не считаются в итоге):{" "}
          {data.archived.map((a) => `${a.name} — оценок: ${a.scores}`).join(", ")}
        </p>
      )}
      {s.error && (
        <p className="text-sm text-danger" role="alert">
          {s.error}
        </p>
      )}

      {editing && (
        <AppModal isOpen size="2xl" title={`Шкала оценок ${data.cohort_code}`} onClose={() => setEditing(false)}>
          <p className="mb-4 text-sm text-default-500">
            {own
              ? "Своя шкала потока. Баллы в сумме — ровно 100."
              : "Сейчас поток идёт по стандарту академии. После сохранения у потока будет своя шкала."}
            {data.completed && " Поток завершён: статусы выпускников не изменятся, пока вы не нажмёте «Пересчитать выпускников»."}
          </p>
          <SchemeEditor
            initial={data.scheme}
            saving={s.save.pending}
            onCancel={() => setEditing(false)}
            onSave={(draft) => void s.run(draft)}
          />
        </AppModal>
      )}
      <ConflictDialog save={s.save} />
      {s.archive && (
        <ArchiveConfirm names={s.archive} pending={s.save.pending} onClose={s.dismiss} onConfirm={() => void s.confirm()} />
      )}
      {resetting && (
        <ConfirmModal
          confirmLabel={resetting === "archive" ? "Вернуть, оценки в архив" : "Вернуть стандарт"}
          isLoading={resetBusy}
          isOpen
          title="Вернуть стандарт академии?"
          onClose={() => setResetting(null)}
          onConfirm={() => void reset(resetting === "archive")}
        >
          {resetting === "archive"
            ? "У категорий, которых нет в стандарте академии, есть оценки. Они сохранятся в архиве и перестанут считаться в итоге."
            : "Своя шкала потока удалится, итоги пересчитаются по стандарту академии."}
        </ConfirmModal>
      )}
      {recalc && <RecalcModal cohortId={data.cohort_id} onClose={() => setRecalc(false)} onDone={() => refresh()} />}
    </section>
  );
}

const STATUS_TEXT: Record<string, string> = { выпускник: "станет выпускником", завершил: "перестанет быть выпускником" };

function RecalcModal({ cohortId, onClose, onDone }: { cohortId: string; onClose: () => void; onDone: () => void }) {
  const queryClient = useQueryClient();
  const preview = useQuery({
    queryKey: ["graduation-preview", cohortId],
    queryFn: () => api<Recalc>(`/api/v1/cohorts/${cohortId}/graduation-preview`),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changes = preview.data?.changes ?? [];

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      const done = await api<Recalc>(`/api/v1/cohorts/${cohortId}/graduation-recalc?expected=${changes.length}`, {
        method: "POST",
      });

      notify(`Статусы обновлены: ${done.changes.length}`);
      void queryClient.invalidateQueries({ queryKey: ["cohort", cohortId] });
      void queryClient.invalidateQueries({ queryKey: ["enrollments"] });
      onDone();
      onClose();
    } catch (e) {
      if (isApiError(e) && e.code === "stale_version") {
        setError("Итоги изменились, пока открыт список. Проверьте его ещё раз.");
        void preview.refetch();
      } else setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Закрыть
          </Button>
          <LoadingButton color="primary" isDisabled={changes.length === 0} isLoading={busy} onPress={() => void apply()}>
            Применить
          </LoadingButton>
        </>
      }
      guard={false}
      isOpen
      size="md"
      title="Пересчитать выпускников"
      onClose={onClose}
    >
      {preview.data ? (
        <div className="space-y-4 text-sm">
          {changes.length === 0 ? (
            <p>По текущей шкале статусы не меняются.</p>
          ) : (
            <>
              <p>По текущей шкале изменятся статусы:</p>
              <ul className="space-y-1">
                {changes.map((c) => (
                  <li key={c.enrollment_id} className="flex justify-between gap-3">
                    <span>{c.student_name}</span>
                    <span className={c.new_status === "выпускник" ? "text-success-700 dark:text-success" : "text-warning-700 dark:text-warning"}>
                      {STATUS_TEXT[c.new_status]} · {c.total}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {preview.data.skipped.length > 0 && (
            <div>
              <p className="text-default-500">Не меняются:</p>
              <ul className="space-y-1 text-default-500">
                {preview.data.skipped.map((c) => (
                  <li key={c.enrollment_id}>
                    {c.student_name} — {c.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {error && (
            <p className="text-danger" role="alert">
              {error}
            </p>
          )}
        </div>
      ) : preview.isError ? (
        <ErrorState retrying={preview.isFetching} text="Не удалось посчитать" onRetry={() => void preview.refetch()} />
      ) : (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Bone key={i} className="h-5 w-full" />
          ))}
        </div>
      )}
    </AppModal>
  );
}
