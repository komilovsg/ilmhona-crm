"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Spinner } from "@heroui/spinner";

import { CohortFormModal } from "../CohortFormModal";

import { LessonsTab } from "./LessonsTab";
import { StudentsTab } from "./StudentsTab";

import { ConfirmModal } from "@/components/ConfirmModal";
import { FillBar } from "@/components/FillBar";
import { Icon } from "@/components/Icon";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { CohortStatus } from "@/components/StatusChip";
import { useCanChange, useRefreshEducation } from "@/hooks/education";
import { api, isApiError } from "@/lib/api";
import { daysLabel, formatPrice, fullDate } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { CohortRow } from "@/lib/types";

type Tab = "students" | "lessons";
type Action = "cancel" | "restore" | "delete";

const CONFIRM: Record<Action, { title: string; label: string; text: string; danger: boolean }> = {
  cancel: {
    title: "Отменить поток",
    label: "Отменить поток",
    text: "Поток получит статус «отменён» (это не меняется само), будущие уроки отменятся, аудитория освободится.",
    danger: true,
  },
  restore: {
    title: "Вернуть поток",
    label: "Вернуть",
    text: "Статус снова определится по датам, будущие уроки создадутся заново по расписанию.",
    danger: false,
  },
  delete: {
    title: "Удалить поток",
    label: "Удалить",
    text: "Поток и его расписание будут удалены. Если в потоке есть студенты, система не даст это сделать.",
    danger: true,
  },
};

function Info({ icon, label, children }: { icon: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 rounded-lg bg-primary/10 p-2 text-brand-text">
        <Icon name={icon} size={16} />
      </span>
      <div className="min-w-0">
        <div className="text-xs text-default-500">{label}</div>
        <div className="truncate text-sm font-medium">{children}</div>
      </div>
    </div>
  );
}

export default function CohortPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const refresh = useRefreshEducation();
  const canChange = useCanChange("cohorts");
  const [tab, setTab] = useState<Tab>("students");
  const [editing, setEditing] = useState(false);
  const [action, setAction] = useState<Action | null>(null);

  const cohort = useQuery({ queryKey: ["cohort", id], queryFn: () => api<CohortRow>(`/api/v1/cohorts/${id}`) });

  const run = useMutation({
    mutationFn: (kind: Action) =>
      kind === "delete"
        ? api(`/api/v1/cohorts/${id}`, { method: "DELETE" })
        : api(`/api/v1/cohorts/${id}/${kind}`, { method: "POST" }),
    onSuccess: (_, kind) => {
      void refresh();
      setAction(null);
      if (kind === "delete") {
        notify("Поток удалён");
        router.replace("/cohorts");
      } else notify(kind === "cancel" ? "Поток отменён" : "Поток возвращён");
    },
    onError: (e) => {
      setAction(null);
      notifyError(e);
    },
  });
  const confirm = useSubmit(() => action ? run.mutateAsync(action) : Promise.resolve());

  if (cohort.isPending)
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );

  if (cohort.isError || !cohort.data)
    return (
      <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">
        {isApiError(cohort.error) && cohort.error.status === 404 ? "Поток не найден." : "Не удалось загрузить поток."}{" "}
        <Link className="text-brand-text" href="/cohorts">
          К списку потоков
        </Link>
      </p>
    );

  const c = cohort.data;
  const cancelled = c.status === "отменён";
  const menu = canChange
    ? [
        { key: "edit", label: "Изменить", icon: "edit" },
        cancelled
          ? { key: "restore", label: "Вернуть поток", icon: "check" }
          : { key: "cancel", label: "Отменить поток", icon: "ban", danger: true },
        { key: "delete", label: "Удалить", icon: "trash", danger: true },
      ]
    : [];

  return (
    <>
      <Link className="mb-3 inline-flex items-center gap-1 text-sm text-default-500 hover:text-foreground" href="/cohorts">
        <Icon name="chevron-left" size={16} />
        Потоки
      </Link>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold">{c.code}</h1>
            <CohortStatus status={c.status} />
          </div>
          <p className="text-default-600">{c.course_name}</p>
        </div>
        {menu.length > 0 && (
          <RowMenu
            actions={menu}
            label="Действия с потоком"
            onAction={(k) => (k === "edit" ? setEditing(true) : setAction(k as Action))}
          />
        )}
      </div>

      <section className="mb-5 grid gap-4 rounded-2xl bg-content1 p-4 sm:grid-cols-2 lg:grid-cols-3">
        <Info icon="instructors" label="Инструктор">
          {c.instructor_name ?? "не назначен"}
        </Info>
        <Info icon="calendar" label="Даты">
          {fullDate(c.start_date)} – {fullDate(c.end_date)}
        </Info>
        <Info icon="clock" label="Расписание">
          {daysLabel(c.weekdays)} · {c.start_time}–{c.end_time}
        </Info>
        <Info icon="rooms" label="Аудитория">
          {c.room_name} · {c.branch_name}
        </Info>
        <Info icon="payments" label="Цена в месяц">
          {formatPrice(c.price_month)}
        </Info>
        <div className="flex items-center">
          <div className="w-full">
            <FillBar fill={c.fill} />
          </div>
        </div>
      </section>

      <Segmented
        className="mb-4"
        label="Раздел потока"
        options={[
          { key: "students", label: "Студенты" },
          { key: "lessons", label: "Расписание" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "students" ? (
        <StudentsTab canChange={canChange} cohort={c} />
      ) : (
        <LessonsTab canChange={canChange} cohort={c} />
      )}

      {editing && <CohortFormModal cohort={c} onClose={() => setEditing(false)} />}
      {action && (
        <ConfirmModal
          confirmLabel={CONFIRM[action].label}
          danger={CONFIRM[action].danger}
          isLoading={run.isPending}
          isOpen
          title={CONFIRM[action].title}
          onClose={() => setAction(null)}
          onConfirm={() => confirm()}
        >
          {CONFIRM[action].text}
        </ConfirmModal>
      )}
    </>
  );
}
