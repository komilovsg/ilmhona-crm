"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useMutation, useQuery } from "@tanstack/react-query";

import { StudentEmployment } from "./StudentEmployment";

import { ConfirmModal } from "@/components/ConfirmModal";
import { Icon } from "@/components/Icon";
import { MonthStates } from "@/components/MonthStates";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ReviewChip } from "@/components/ReviewChip";
import { RowMenu } from "@/components/RowMenu";
import { Bone, DetailSkeleton } from "@/components/Skeletons";
import { CohortStatus, PersonStatus } from "@/components/StatusChip";
import { ExportButton } from "@/components/ExportButton";
import { useCanChange, useRefreshEducation } from "@/hooks/education";
import { useSeesPayments } from "@/hooks/money";
import { api } from "@/lib/api";
import { dushanbeDay, telHref } from "@/lib/format";
import { fullDate } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { EnrollmentPayments } from "@/lib/money-types";
import type { StudentDetail } from "@/lib/types";

const StudentFormModal = dynamic(() => import("../StudentFormModal").then((m) => m.StudentFormModal));

/** The months of one enrollment: оплачен / частично: A из B / не оплачен. */
function EnrollmentMonths({ enrollmentId }: { enrollmentId: string }) {
  const money = useQuery({
    queryKey: ["cohort-payments", "enrollment", enrollmentId],
    queryFn: () => api<EnrollmentPayments>(`/api/v1/payments/enrollment/${enrollmentId}`),
  });

  if (money.isPending) return <Bone className="h-5 w-24 rounded-md" />;
  if (!money.data) return <span className="text-default-400">—</span>;

  return <MonthStates states={money.data.month_states} />;
}

export default function StudentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const refresh = useRefreshEducation();
  const canChange = useCanChange("students");
  const seesPayments = useSeesPayments();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const student = useQuery({ queryKey: ["student", id], queryFn: () => api<StudentDetail>(`/api/v1/students/${id}`) });

  const remove = useMutation({
    mutationFn: () => api(`/api/v1/students/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      notify("Студент удалён");
      router.replace("/students");
    },
    onError: (e) => {
      setDeleting(false);
      notifyError(e);
    },
  });
  const confirm = useSubmit(() => remove.mutateAsync());
  const clear = useMutation({
    mutationFn: (version: number) =>
      api(`/api/v1/students/${id}`, { method: "PATCH", body: { needs_review: false }, version }),
    onSuccess: () => {
      void refresh();
      notify("Отметка снята");
    },
    onError: (e) => {
      void refresh();
      notifyError(e);
    },
  });

  if (student.data === undefined)
    return (
      <QueryState
        errorText="Не удалось загрузить студента"
        notFound={
          <EmptyState
            action={
              <Link className="text-brand-text" href="/students">
                К списку студентов
              </Link>
            }
            title="Студент не найден"
          />
        }
        query={student}
        skeleton={<DetailSkeleton cells={0} />}
      >
        {null}
      </QueryState>
    );

  const s = student.data;

  return (
    <>
      <Link className="mb-3 inline-flex items-center gap-1 text-sm text-default-500 hover:text-foreground" href="/students">
        <Icon name="chevron-left" size={16} />
        Студенты
      </Link>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold">{s.full_name}</h1>
            <PersonStatus status={s.status} />
          </div>
          <p className="mt-1 text-sm text-default-600">
            {s.branch_name} · добавлен {fullDate(dushanbeDay(s.created_at))}
            {s.gender && ` · ${s.gender === "male" ? "мужской" : "женский"}`}
          </p>
          {s.needs_review && (
            <div className="mt-2">
              <ReviewChip
                clearing={clear.isPending}
                reason={s.review_reason}
                onClear={canChange ? () => clear.mutate(s.version) : undefined}
              />
            </div>
          )}
          {s.phone && (
            <a className="mt-2 inline-flex items-center gap-1.5 text-brand-text" href={telHref(s.phone)}>
              <Icon name="phone" size={16} />
              {s.phone}
            </a>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ExportButton path={`/api/v1/students/${s.id}/export`} />
          {canChange && (
            <RowMenu
              actions={[
                { key: "edit", label: "Изменить", icon: "edit" },
                { key: "delete", label: "Удалить", icon: "trash", danger: true },
              ]}
              label="Действия со студентом"
              onAction={(k) => (k === "edit" ? setEditing(true) : setDeleting(true))}
            />
          )}
        </div>
      </div>

      <h2 className="mb-3 text-lg font-semibold">История зачислений</h2>
      {s.enrollments.length === 0 ? (
        <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">Студент пока не зачислен ни в один поток.</p>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Поток</th>
                  <th className="px-4 py-3 font-medium">Курс</th>
                  <th className="px-4 py-3 font-medium">Даты</th>
                  <th className="px-4 py-3 font-medium">Поток</th>
                  <th className="px-4 py-3 font-medium">Зачисление</th>
                  {seesPayments && <th className="px-4 py-3 font-medium">Месяцы</th>}
                </tr>
              </thead>
              <tbody>
                {s.enrollments.map((e) => (
                  <tr key={e.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                    <td className="px-4 py-3 font-medium">
                      <Link className="text-brand-text" href={`/cohorts/${e.cohort_id}`}>
                        {e.cohort_code}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{e.course_name}</td>
                    <td className="px-4 py-3 text-default-600">
                      {fullDate(e.start_date)} – {fullDate(e.end_date)}
                    </td>
                    <td className="px-4 py-3">
                      <CohortStatus status={e.cohort_status} />
                    </td>
                    <td className="px-4 py-3">
                      <PersonStatus status={e.status} />
                      {e.needs_review && (
                        <div className="mt-1">
                          <ReviewChip reason={e.review_reason} />
                        </div>
                      )}
                    </td>
                    {seesPayments && (
                      <td className="px-4 py-3">
                        <EnrollmentMonths enrollmentId={e.id} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul data-rows className="space-y-3 md:hidden">
            {s.enrollments.map((e) => (
              <li key={e.id} className="rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link className="font-medium text-brand-text" href={`/cohorts/${e.cohort_id}`}>
                      {e.cohort_code}
                    </Link>
                    <div className="truncate text-sm">{e.course_name}</div>
                  </div>
                  <PersonStatus status={e.status} />
                </div>
                {e.needs_review && (
                  <div className="mt-2">
                    <ReviewChip reason={e.review_reason} />
                  </div>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-default-600">
                  {fullDate(e.start_date)} – {fullDate(e.end_date)}
                  <CohortStatus status={e.cohort_status} />
                </div>
                {seesPayments && (
                  <div className="mt-2">
                    <EnrollmentMonths enrollmentId={e.id} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      <StudentEmployment
        graduateEnrollmentId={s.enrollments.find((e) => e.status === "выпускник")?.id ?? null}
        student={{ id: s.id, name: s.full_name }}
      />

      {editing && <StudentFormModal student={s} onClose={() => setEditing(false)} />}
      {deleting && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Удалить студента"
          onClose={() => setDeleting(false)}
          onConfirm={() => confirm()}
        >
          {s.full_name} будет удалён. Если он зачислен в потоки, система не даст это сделать.
        </ConfirmModal>
      )}
    </>
  );
}
