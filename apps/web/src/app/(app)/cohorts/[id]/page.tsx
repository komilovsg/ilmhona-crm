"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";


import { FinishModal, ReopenModal } from "./FinishModal";
import { StudentsTab } from "./StudentsTab";

import { ConfirmModal } from "@/components/ConfirmModal";
import { FillBar } from "@/components/FillBar";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { DetailSkeleton, ListSkeleton } from "@/components/Skeletons";
import { CohortStatus, OverdueChip } from "@/components/StatusChip";
import { useCanMark, useCanSeeAttendance } from "@/hooks/attendance";
import { useCanIssueCerts } from "@/hooks/certs";
import { useCanChange, useRefreshEducation } from "@/hooks/education";
import { useIsSuperadmin } from "@/hooks/goals";
import { api } from "@/lib/api";
import { cohortTitle, daysLabel, formatPrice, fullDate } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { CohortRow, EnrollmentRow } from "@/lib/types";
import { lazyModal } from "@/lib/lazy-modal";

// Tabs other than the first load on demand; the skeleton keeps the height while the chunk arrives.
const tabLoading = () => <ListSkeleton />;
const LessonsTab = dynamic(() => import("./LessonsTab").then((m) => m.LessonsTab), { loading: tabLoading });
const AttendanceTab = dynamic(() => import("./AttendanceTab").then((m) => m.AttendanceTab), { loading: tabLoading });
const AnalyticsTab = dynamic(() => import("./AnalyticsTab").then((m) => m.AnalyticsTab), { loading: tabLoading });
const GradesTab = dynamic(() => import("./GradesTab").then((m) => m.GradesTab), { loading: tabLoading });
const IssueCertificatesModal = lazyModal(() => import("@/components/certs/IssueCertificatesModal").then((m) => m.IssueCertificatesModal));
const CohortFormModal = lazyModal(() => import("../CohortFormModal").then((m) => m.CohortFormModal));

type Tab = "students" | "lessons" | "attendance" | "grades" | "analytics";
const TABS: Tab[] = ["students", "lessons", "attendance", "grades", "analytics"];
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
    text: "Статус снова определится по дате начала, будущие уроки создадутся заново по расписанию.",
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
        <div className="break-words text-sm font-medium">{children}</div>
      </div>
    </div>
  );
}

export default function CohortPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const refresh = useRefreshEducation();
  const canChange = useCanChange("cohorts");
  const canMark = useCanMark();
  const isSuperadmin = useIsSuperadmin();
  const seesAttendance = useCanSeeAttendance();
  const params = useSearchParams();
  const wanted = params.get("tab");
  // a link from elsewhere (`?tab=attendance&student=<enrollment>`) opens that tab
  const [tab, setTab] = useState<Tab>(TABS.find((t) => t === wanted) ?? "students");
  const focusStudent = params.get("student");
  const [seenTab, setSeenTab] = useState(wanted);

  // the address changed under the page (a link from the analytics tab): follow it
  if (wanted !== seenTab) {
    setSeenTab(wanted);
    const next = TABS.find((t) => t === wanted);

    if (next) setTab(next);
  }
  const [editing, setEditing] = useState(false);
  const [issuingCerts, setIssuingCerts] = useState(false);
  const canIssue = useCanIssueCerts();
  const enrollments = useQuery({
    queryKey: ["enrollments", id],
    queryFn: () => api<EnrollmentRow[]>(`/api/v1/cohorts/${id}/enrollments`),
    enabled: canIssue,
  });
  const graduates = enrollments.data?.filter((e) => e.status === "выпускник").length ?? 0;
  const [action, setAction] = useState<Action | null>(null);
  const [closing, setClosing] = useState<"finish" | "reopen" | null>(null);

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

  if (cohort.data === undefined)
    return (
      <QueryState
        errorText="Не удалось загрузить поток"
        notFound={
          <EmptyState
            action={
              <Link className="text-brand-text" href="/cohorts">
                К списку потоков
              </Link>
            }
            title="Поток не найден"
          />
        }
        query={cohort}
        skeleton={<DetailSkeleton />}
      >
        {null}
      </QueryState>
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
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold">{c.code}</h1>
            <CohortStatus status={c.status} />
            {c.overdue && <OverdueChip />}
            {!!c.instructor_conflicts && (
              <Chip
                color="warning"
                size="sm"
                title={`Уроков, которые пересекаются с другим уроком инструктора: ${c.instructor_conflicts}. Перенесите или отмените их во вкладке «Расписание».`}
                variant="flat"
              >
                Проверить: конфликт инструктора
              </Chip>
            )}
          </div>
          <p className="break-words text-default-600">{cohortTitle(c)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
          {canChange && c.status === "активный" && (
            <Button
              color={c.overdue ? "primary" : "default"}
              startContent={<Icon name="check" size={18} />}
              variant={c.overdue ? "solid" : "flat"}
              onPress={() => setClosing("finish")}
            >
              Завершить поток
            </Button>
          )}
          {isSuperadmin && c.status === "завершён" && !c.certificates_issued && (
            <Button variant="flat" onPress={() => setClosing("reopen")}>
              Вернуть в активные
            </Button>
          )}
          {canIssue && (
            <span
              className="shrink-0"
              title={c.status !== "завершён" ? "Сначала завершите поток" : graduates === 0 ? "В потоке нет выпускников" : undefined}
            >
              <Button
                color="primary"
                isDisabled={c.status !== "завершён" || graduates === 0}
                startContent={<Icon name="certificate" size={18} />}
                variant="flat"
                onPress={() => setIssuingCerts(true)}
              >
                Выдать сертификаты
              </Button>
            </span>
          )}
          {menu.length > 0 && (
            <RowMenu
              actions={menu}
              label="Действия с потоком"
              onAction={(k) => (k === "edit" ? setEditing(true) : setAction(k as Action))}
            />
          )}
        </div>
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
          ...(seesAttendance
            ? [
                { key: "attendance" as const, label: "Посещаемость" },
                { key: "grades" as const, label: "Оценки" },
                { key: "analytics" as const, label: "Аналитика" },
              ]
            : []),
        ]}
        value={tab}
        onChange={(t) => {
          setTab(t);
          // the address names the tab, so a reload (and a copied link) opens the same one
          router.replace(`?tab=${t}`, { scroll: false });
        }}
      />
      {tab === "students" && <StudentsTab canChange={canChange} cohort={c} />}
      {tab === "lessons" && <LessonsTab canChange={canChange} cohort={c} />}
      {tab === "attendance" && <AttendanceTab canMark={canMark} cohortId={c.id} focusEnrollment={focusStudent} />}
      {tab === "grades" && <GradesTab canMark={canMark} cohortId={c.id} />}
      {tab === "analytics" && seesAttendance && <AnalyticsTab cohortId={c.id} />}

      {issuingCerts && <IssueCertificatesModal cohortId={c.id} onClose={() => setIssuingCerts(false)} />}
      {closing === "finish" && <FinishModal cohort={c} onClose={() => setClosing(null)} />}
      {closing === "reopen" && <ReopenModal cohort={c} onClose={() => setClosing(null)} />}
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
