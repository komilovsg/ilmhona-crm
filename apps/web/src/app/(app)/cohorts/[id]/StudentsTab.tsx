"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";
import { Spinner } from "@heroui/spinner";

import { EnrollModal } from "./modals";

import { ConfirmModal } from "@/components/ConfirmModal";
import { Icon } from "@/components/Icon";
import { PersonStatus } from "@/components/StatusChip";
import { useRefreshEducation } from "@/hooks/education";
import { api } from "@/lib/api";
import { ENROLLMENT_STATUSES } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { CohortRow, EnrollmentRow } from "@/lib/types";

function StatusMenu({ row, onPick }: { row: EnrollmentRow; onPick: (status: string) => void }) {
  return (
    <Dropdown placement="bottom-end">
      <DropdownTrigger>
        <Button aria-label={`Статус: ${row.student_name}`} endContent={<Icon name="chevron-right" size={14} className="rotate-90" />} size="sm" variant="flat">
          {row.status}
        </Button>
      </DropdownTrigger>
      <DropdownMenu
        aria-label="Статус зачисления"
        disabledKeys={[row.status]}
        onAction={(key) => onPick(String(key))}
      >
        {ENROLLMENT_STATUSES.map((s) => (
          <DropdownItem key={s}>{s}</DropdownItem>
        ))}
      </DropdownMenu>
    </Dropdown>
  );
}

export function StudentsTab({ cohort, canChange }: { cohort: CohortRow; canChange: boolean }) {
  const refresh = useRefreshEducation();
  const [enrolling, setEnrolling] = useState(false);
  const [removing, setRemoving] = useState<EnrollmentRow | null>(null);
  const open = cohort.status === "набор" || cohort.status === "активный";

  const list = useQuery({
    queryKey: ["enrollments", cohort.id],
    queryFn: () => api<EnrollmentRow[]>(`/api/v1/cohorts/${cohort.id}/enrollments`),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status, version }: { id: string; status: string; version: number }) =>
      api(`/api/v1/enrollments/${id}`, { method: "PATCH", body: { status }, version }),
    onSuccess: () => void refresh(),
    onError: (e) => {
      void refresh(); // a 409 means somebody changed it first: show what is there now
      notifyError(e);
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/v1/enrollments/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      notify("Студент убран из потока");
      setRemoving(null);
    },
    onError: (e) => {
      setRemoving(null);
      notifyError(e);
    },
  });
  const confirm = useSubmit(() => removing ? remove.mutateAsync(removing.id) : Promise.resolve());

  const rows = list.data ?? [];
  const phone = (r: EnrollmentRow) =>
    r.phone ? (
      <a className="text-brand-text" href={`tel:${r.phone}`}>
        {r.phone}
      </a>
    ) : (
      "—"
    );
  const status = (r: EnrollmentRow) =>
    canChange ? <StatusMenu row={r} onPick={(s) => setStatus.mutate({ id: r.id, status: s, version: r.version })} /> : <PersonStatus status={r.status} />;
  const trash = (r: EnrollmentRow) =>
    canChange && (
      <Button isIconOnly aria-label={`Убрать: ${r.student_name}`} color="danger" size="sm" variant="light" onPress={() => setRemoving(r)}>
        <Icon name="trash" size={16} />
      </Button>
    );

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-default-600">
          Студентов: <b>{cohort.fill.enrolled}</b> из {cohort.fill.capacity}
        </p>
        {canChange && open && (
          <Button color="primary" startContent={<Icon name="user-plus" size={18} />} onPress={() => setEnrolling(true)}>
            Добавить студента
          </Button>
        )}
      </div>

      {list.isPending ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">В потоке пока нет студентов.</p>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Студент</th>
                  <th className="px-4 py-3 font-medium">Телефон</th>
                  <th className="px-4 py-3 font-medium">Статус</th>
                  <th className="w-12" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                    <td className="px-4 py-3 font-medium">
                      <Link className="hover:text-brand-text" href={`/students/${r.student_id}`}>
                        {r.student_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{phone(r)}</td>
                    <td className="px-4 py-2">{status(r)}</td>
                    <td className="px-2">{trash(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-3 md:hidden">
            {rows.map((r) => (
              <li key={r.id} className="rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <Link className="min-w-0 truncate font-medium" href={`/students/${r.student_id}`}>
                    {r.student_name}
                  </Link>
                  {trash(r)}
                </div>
                <div className="mt-1 text-sm">{phone(r)}</div>
                <div className="mt-2">{status(r)}</div>
              </li>
            ))}
          </ul>
        </>
      )}

      {enrolling && <EnrollModal cohort={cohort} onClose={() => setEnrolling(false)} />}
      {removing && (
        <ConfirmModal
          confirmLabel="Убрать"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Убрать студента из потока"
          onClose={() => setRemoving(null)}
          onConfirm={() => confirm()}
        >
          {removing.student_name} будет убран из потока {cohort.code}. Сам студент останется в списке студентов.
        </ConfirmModal>
      )}
    </>
  );
}
