"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import clsx from "clsx";


import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { RowMenu } from "@/components/RowMenu";
import { useRefreshEducation } from "@/hooks/education";
import { api } from "@/lib/api";
import { dayTitle, fullDate, todayIso } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { CohortRow, LessonRow } from "@/lib/types";

const LessonFormModal = dynamic(() => import("./modals").then((m) => m.LessonFormModal));

export function LessonsTab({ cohort, canChange }: { cohort: CohortRow; canChange: boolean }) {
  const refresh = useRefreshEducation();
  const [form, setForm] = useState<LessonRow | "new" | null>(null);
  const [cancelling, setCancelling] = useState<LessonRow | null>(null);
  const today = todayIso();
  const open = cohort.status === "набор" || cohort.status === "активный";

  const list = useQuery({
    queryKey: ["lessons", cohort.id],
    queryFn: () => api<LessonRow[]>(`/api/v1/cohorts/${cohort.id}/lessons`),
  });

  const cancel = useMutation({
    mutationFn: (id: string) => api(`/api/v1/lessons/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      void refresh();
      notify("Урок отменён");
      setCancelling(null);
    },
    onError: (e) => {
      setCancelling(null);
      notifyError(e);
    },
  });
  const confirm = useSubmit(() => cancelling ? cancel.mutateAsync(cancelling.id) : Promise.resolve());

  const lessons = list.data ?? [];
  const live = lessons.filter((l) => !l.cancelled).length;
  const menu = (l: LessonRow) =>
    canChange &&
    open &&
    !l.cancelled && (
      <RowMenu
        actions={[
          { key: "move", label: "Перенести", icon: "edit" },
          { key: "cancel", label: "Отменить урок", icon: "ban", danger: true },
        ]}
        label={`Действия: урок ${fullDate(l.date)}`}
        onAction={(k) => (k === "move" ? setForm(l) : setCancelling(l))}
      />
    );
  const state = (l: LessonRow) =>
    l.cancelled ? (
      <Chip color="danger" size="sm" variant="flat">
        отменён
      </Chip>
    ) : l.date < today ? (
      <span className="text-default-500">прошёл</span>
    ) : l.date === today ? (
      <Chip color="primary" size="sm" variant="flat">
        сегодня
      </Chip>
    ) : null;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-default-600">
          Уроков: <b>{live}</b>
          {live !== lessons.length && <span className="text-default-500"> (отменённых {lessons.length - live})</span>}
        </p>
        <div className="flex items-center gap-2">
          <ExportButton path={`/api/v1/cohorts/${cohort.id}/lessons/export`} />
          {canChange && open && (
            <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setForm("new")}>
              Добавить урок
            </Button>
          )}
        </div>
      </div>

      <QueryState
        empty={
          <EmptyState
            action={
              canChange && open ? (
                <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setForm("new")}>
                  Добавить урок
                </Button>
              ) : undefined
            }
            title="Уроков пока нет"
          />
        }
        isEmpty={(d) => d.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={5} rows={5} />}
      >
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Дата</th>
                  <th className="px-4 py-3 font-medium">Время</th>
                  <th className="px-4 py-3 font-medium">Аудитория</th>
                  <th className="px-4 py-3 font-medium">Статус</th>
                  <th className="w-12" />
                </tr>
              </thead>
              <tbody>
                {lessons.map((l) => (
                  <tr
                    key={l.id}
                    className={clsx(
                      "border-b border-divider last:border-0 hover:bg-default-50",
                      (l.cancelled || l.date < today) && "text-default-500",
                      l.cancelled && "line-through decoration-default-400",
                    )}
                  >
                    <td className="px-4 py-3 font-medium">
                      {dayTitle(l.date)}.{l.date.slice(0, 4)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {l.start}–{l.end}
                    </td>
                    <td className="px-4 py-3">{l.room_name}</td>
                    <td className="px-4 py-3 no-underline">{state(l)}</td>
                    <td className="px-2">{menu(l)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul data-rows className="space-y-2 md:hidden">
            {lessons.map((l) => (
              <li
                key={l.id}
                className={clsx(
                  "flex items-center justify-between gap-2 rounded-2xl bg-content1 p-4",
                  (l.cancelled || l.date < today) && "opacity-70",
                )}
              >
                <div>
                  <div className={clsx("font-medium", l.cancelled && "line-through")}>
                    {dayTitle(l.date)}.{l.date.slice(0, 4)}
                  </div>
                  <div className="text-sm tabular-nums text-default-600">
                    {l.start}–{l.end} · {l.room_name}
                  </div>
                  <div className="mt-1 text-sm">{state(l)}</div>
                </div>
                {menu(l)}
              </li>
            ))}
          </ul>
        </>
      </QueryState>

      {form && <LessonFormModal cohort={cohort} lesson={form === "new" ? null : form} onClose={() => setForm(null)} />}
      {cancelling && (
        <ConfirmModal
          confirmLabel="Отменить урок"
          danger
          isLoading={cancel.isPending}
          isOpen
          title="Отменить урок"
          onClose={() => setCancelling(null)}
          onConfirm={() => confirm()}
        >
          Урок {fullDate(cancelling.date)}, {cancelling.start}–{cancelling.end} будет отменён, аудитория освободится.
        </ConfirmModal>
      )}
    </>
  );
}
