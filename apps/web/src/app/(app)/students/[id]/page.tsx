"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";

import { StudentFormModal } from "../StudentFormModal";
import { StudentEmployment } from "./StudentEmployment";

import { ConfirmModal } from "@/components/ConfirmModal";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { DetailSkeleton } from "@/components/Skeletons";
import { CohortStatus, PersonStatus } from "@/components/StatusChip";
import { useCanChange, useRefreshEducation } from "@/hooks/education";
import { api } from "@/lib/api";
import { dushanbeDay, telHref } from "@/lib/format";
import { fullDate } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { StudentDetail } from "@/lib/types";

export default function StudentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const refresh = useRefreshEducation();
  const canChange = useCanChange("students");
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
          {s.phone && (
            <a className="mt-2 inline-flex items-center gap-1.5 text-brand-text" href={telHref(s.phone)}>
              <Icon name="phone" size={16} />
              {s.phone}
            </a>
          )}
        </div>
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-3 md:hidden">
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
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-default-600">
                  {fullDate(e.start_date)} – {fullDate(e.end_date)}
                  <CohortStatus status={e.cohort_status} />
                </div>
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
