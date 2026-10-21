"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";

import { EnrollModal } from "./modals";

import { PaymentFormModal } from "../../payments/PaymentFormModal";

import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { ReviewChip } from "@/components/ReviewChip";
import { PersonStatus } from "@/components/StatusChip";
import { useRefreshEducation } from "@/hooks/education";
import { useCanPay, useSeesPayments } from "@/hooks/money";
import { api } from "@/lib/api";
import { telHref } from "@/lib/format";
import { ENROLLMENT_STATUSES, formatPrice } from "@/lib/education";
import { paidMonthsLabel } from "@/lib/money";
import type { CohortPayments } from "@/lib/money-types";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { CohortRow, EnrollmentRow } from "@/lib/types";
import { useOverlayMotion } from "@/lib/motion";

function StatusMenu({ row, onPick }: { row: EnrollmentRow; onPick: (status: string) => void }) {
  const overlayMotion = useOverlayMotion();
  return (
    <Dropdown motionProps={overlayMotion} placement="bottom-end">
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
  const [paying, setPaying] = useState<string | null>(null);
  const seesMoney = useSeesPayments();
  const canPay = useCanPay();
  const open = cohort.status === "набор" || cohort.status === "активный";

  const list = useQuery({
    queryKey: ["enrollments", cohort.id],
    queryFn: () => api<EnrollmentRow[]>(`/api/v1/cohorts/${cohort.id}/enrollments`),
  });

  const money = useQuery({
    queryKey: ["cohort-payments", cohort.id],
    queryFn: () => api<CohortPayments>(`/api/v1/payments/by-cohort/${cohort.id}`),
    enabled: seesMoney,
  });
  const moneyOf = new Map(money.data?.items.map((m) => [m.enrollment_id, m]));

  const setStatus = useMutation({
    mutationFn: ({ id, status, version }: { id: string; status: string; version: number }) =>
      api(`/api/v1/enrollments/${id}`, { method: "PATCH", body: { status }, version }),
    onSuccess: () => void refresh(),
    onError: (e) => {
      void refresh(); // a 409 means somebody changed it first: show what is there now
      notifyError(e);
    },
  });

  const clear = useMutation({
    mutationFn: (r: EnrollmentRow) =>
      api(`/api/v1/enrollments/${r.id}/review`, { method: "PATCH", body: { needs_review: false }, version: r.version }),
    onSuccess: () => {
      void refresh();
      notify("Отметка снята");
    },
    onError: (e) => {
      void refresh();
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
  const flag = (r: EnrollmentRow) =>
    r.needs_review && (
      <div className="mt-1">
        <ReviewChip
          clearing={clear.isPending && clear.variables?.id === r.id}
          reason={r.review_reason}
          onClear={canChange ? () => clear.mutate(r) : undefined}
        />
      </div>
    );
  const phone = (r: EnrollmentRow) =>
    r.phone ? (
      <a className="text-brand-text" href={telHref(r.phone)}>
        {r.phone}
      </a>
    ) : (
      "—"
    );
  const status = (r: EnrollmentRow) =>
    canChange ? <StatusMenu row={r} onPick={(s) => setStatus.mutate({ id: r.id, status: s, version: r.version })} /> : <PersonStatus status={r.status} />;
  const paid = (r: EnrollmentRow) => {
    const m = moneyOf.get(r.id);

    return m ? (
      <>
        <span className="font-medium">{formatPrice(m.paid)}</span>
        <span className="block text-xs text-default-500">{paidMonthsLabel(m.paid_months, money.data?.months ?? 0)}</span>
      </>
    ) : (
      "—"
    );
  };
  const debt = (r: EnrollmentRow) => {
    const m = moneyOf.get(r.id);

    return m && Number(m.debt) > 0 ? <span className="font-semibold text-danger">{formatPrice(m.debt)}</span> : m ? "—" : "";
  };
  const payButton = (r: EnrollmentRow) =>
    canPay &&
    r.status !== "отчислен" &&
    cohort.status !== "отменён" && (
      <Button
        aria-label={`Оплата: ${r.student_name}`}
        color="primary"
        size="sm"
        startContent={<Icon name="payments" size={16} />}
        variant="flat"
        onPress={() => setPaying(r.id)}
      >
        Оплата
      </Button>
    );
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
          {money.data && (
            <>
              {" "}
              · оплатили: <b>{money.data.payers}</b> из {money.data.enrolled}
            </>
          )}
        </p>
        <div className="flex items-center gap-2">
          <ExportButton path={`/api/v1/cohorts/${cohort.id}/enrollments/export`} />
          {canChange && open && (
            <Button color="primary" startContent={<Icon name="user-plus" size={18} />} onPress={() => setEnrolling(true)}>
              Добавить студента
            </Button>
          )}
        </div>
      </div>

      <QueryState
        empty={
          <EmptyState
            action={
              canChange && open ? (
                <Button color="primary" startContent={<Icon name="user-plus" size={18} />} onPress={() => setEnrolling(true)}>
                  Добавить студента
                </Button>
              ) : undefined
            }
            title="В потоке пока нет студентов"
          />
        }
        isEmpty={(d) => d.length === 0}
        query={list}
        skeleton={<ListSkeleton cols={4} rows={5} />}
      >
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Студент</th>
                  <th className="px-4 py-3 font-medium">Телефон</th>
                  <th className="px-4 py-3 font-medium">Статус</th>
                  {seesMoney && (
                    <>
                      <th className="px-4 py-3 font-medium">Оплачено</th>
                      <th className="px-4 py-3 font-medium">Долг</th>
                      <th className="px-4 py-3 text-right font-medium" />
                    </>
                  )}
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
                      {flag(r)}
                    </td>
                    <td className="px-4 py-3">{phone(r)}</td>
                    <td className="px-4 py-2">{status(r)}</td>
                    {seesMoney && (
                      <>
                        <td className="px-4 py-3">{paid(r)}</td>
                        <td className="whitespace-nowrap px-4 py-3">{debt(r)}</td>
                        <td className="px-2 py-2 text-right">{payButton(r)}</td>
                      </>
                    )}
                    <td className="px-2">{trash(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul data-rows className="space-y-3 md:hidden">
            {rows.map((r) => (
              <li key={r.id} className="rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <Link className="min-w-0 truncate font-medium" href={`/students/${r.student_id}`}>
                    {r.student_name}
                  </Link>
                  {trash(r)}
                </div>
                {flag(r)}
                <div className="mt-1 text-sm">{phone(r)}</div>
                <div className="mt-2">{status(r)}</div>
                {seesMoney && (
                  <div className="mt-3 flex items-end justify-between gap-2 border-t border-divider pt-3 text-sm">
                    <div>
                      <div>{paid(r)}</div>
                      <div>Долг: {debt(r)}</div>
                    </div>
                    {payButton(r)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      </QueryState>

      {paying && <PaymentFormModal enrollmentId={paying} payment={null} onClose={() => setPaying(null)} />}
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
