"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";
import { useMenu } from "@/components/useMenu";



import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { MonthStates } from "@/components/MonthStates";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { ReviewChip } from "@/components/ReviewChip";
import { PersonStatus } from "@/components/StatusChip";
import { useIsInstructor, useRefreshEducation } from "@/hooks/education";
import { useCanPay, useSeesPayments } from "@/hooks/money";
import { api } from "@/lib/api";
import { telHref } from "@/lib/format";
import { ENROLLMENT_STATUSES, EXPELLED, expelledLast, formatPrice, fullDate, todayIso } from "@/lib/education";
import type { CohortPayments } from "@/lib/money-types";
import { studentFunding, withDonors } from "@/lib/funding";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { CohortRow, EnrollmentRow } from "@/lib/types";
import { useOverlayMotion } from "@/lib/motion";
import { lazyModal } from "@/lib/lazy-modal";

const EnrollModal = lazyModal(() => import("./modals").then((m) => m.EnrollModal));
const NewStudentModal = lazyModal(() => import("@/components/NewStudentModal").then((m) => m.NewStudentModal));
const EnrollDateModal = lazyModal(() => import("@/components/EnrollDateModal").then((m) => m.EnrollDateModal));
const PaymentFormModal = lazyModal(() => import("../../payments/PaymentFormModal").then((m) => m.PaymentFormModal));

function StatusMenu({ row, onPick }: { row: EnrollmentRow; onPick: (status: string) => void }) {
  const overlayMotion = useOverlayMotion();
  const menu = useMenu(onPick);

  return (
    <Dropdown {...menu.dropdown} motionProps={overlayMotion} placement="bottom-end">
      <DropdownTrigger>
        <Button aria-label={`Статус: ${row.student_name}`} endContent={<Icon name="chevron-right" size={14} className="rotate-90" />} size="sm" color="primary" variant="flat">
          {row.status}
        </Button>
      </DropdownTrigger>
      <DropdownMenu
        aria-label="Статус зачисления"
        disabledKeys={[row.status]}
        onAction={menu.onAction}
      >
        {ENROLLMENT_STATUSES.map((s) => (
          <DropdownItem key={s}>{s}</DropdownItem>
        ))}
      </DropdownMenu>
    </Dropdown>
  );
}

const SELF = "__self__";

/** «Платит сам» ↔ «Донор: X» of one student (a mixed cohort; a donor cohort: another donor only). */
function FundingMenu({ row, cohort, onPick }: { row: EnrollmentRow; cohort: CohortRow; onPick: (donorId: string | null) => void }) {
  const overlayMotion = useOverlayMotion();
  const menu = useMenu((key: string) => onPick(key === SELF ? null : key));
  const options = [
    ...(cohort.funding === "смешанный" ? [{ key: SELF, label: "Платит сам" }] : []),
    ...cohort.donors.filter((d) => !d.archived || d.id === row.donor_id).map((d) => ({ key: d.id, label: `Донор: ${d.name}` })),
  ];
  const label = studentFunding(cohort.funding, row.donor_id, cohort.donors);

  return (
    <Dropdown {...menu.dropdown} motionProps={overlayMotion} placement="bottom-end">
      <DropdownTrigger>
        <Button aria-label={`Кто платит: ${row.student_name}`} className="max-w-full" size="sm" variant="light">
          <span className="truncate">{label}</span>
        </Button>
      </DropdownTrigger>
      <DropdownMenu aria-label="Кто платит" disabledKeys={[row.donor_id ?? SELF]} items={options} onAction={menu.onAction}>
        {(o) => <DropdownItem key={o.key}>{o.label}</DropdownItem>}
      </DropdownMenu>
    </Dropdown>
  );
}

export function StudentsTab({ cohort, canChange }: { cohort: CohortRow; canChange: boolean }) {
  const refresh = useRefreshEducation();
  const [enrolling, setEnrolling] = useState(false);
  const [removing, setRemoving] = useState<EnrollmentRow | null>(null);
  const [paying, setPaying] = useState<string | null>(null);
  const [dating, setDating] = useState<EnrollmentRow | null>(null);
  const seesMoney = useSeesPayments();
  const canPay = useCanPay();
  const open = cohort.status === "набор" || cohort.status === "активный";
  // an instructor adds new students to their own cohort (the only cohorts they see)
  const instructor = useIsInstructor();
  const canAdd = (canChange || instructor) && open;

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

  const setFunding = useMutation({
    mutationFn: ({ r, donorId }: { r: EnrollmentRow; donorId: string | null }) =>
      api(`/api/v1/enrollments/${r.id}/funding`, { method: "PATCH", body: { donor_id: donorId }, version: r.version }),
    onSuccess: () => {
      void refresh();
      void money.refetch();
      notify("Финансирование изменено");
    },
    onError: (e) => {
      void refresh();
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
      notify(instructor ? "Студент удалён" : "Студент убран из потока");
      setRemoving(null);
    },
    onError: (e) => {
      setRemoving(null);
      notifyError(e);
    },
  });
  const confirm = useSubmit(() => removing ? remove.mutateAsync(removing.id) : Promise.resolve());

  const rows = expelledLast(list.data ?? []);
  const firstExpelled = rows.findIndex((r) => r.status === EXPELLED);
  const expelledTitle = `Отчисленные (${firstExpelled < 0 ? 0 : rows.length - firstExpelled})`;
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
  // the enrollment day (Dushanbe): lessons before it take no marks; who may enrol may move it
  const enrolledOn = (r: EnrollmentRow) => todayIso(new Date(r.enrolled_at));
  const enrolled = (r: EnrollmentRow) => (
    <span className="inline-flex items-center gap-1 whitespace-nowrap tabular-nums">
      {fullDate(enrolledOn(r))}
      {(canChange || instructor) && (
        <Button
          isIconOnly
          aria-label={`Изменить дату зачисления: ${r.student_name}`}
          className="size-8 min-w-8"
          size="sm"
          variant="light"
          onPress={() => setDating(r)}
        >
          <Icon name="pen" size={14} />
        </Button>
      )}
    </span>
  );
  const statusOnly = (r: EnrollmentRow) =>
    canChange ? <StatusMenu row={r} onPick={(s) => setStatus.mutate({ id: r.id, status: s, version: r.version })} /> : <PersonStatus status={r.status} />;
  const funding = (r: EnrollmentRow) =>
    withDonors(cohort.funding) &&
    (canChange ? (
      <FundingMenu cohort={cohort} row={r} onPick={(donorId) => setFunding.mutate({ r, donorId })} />
    ) : (
      <span className="text-xs text-default-500">{studentFunding(cohort.funding, r.donor_id, cohort.donors)}</span>
    ));
  const status = (r: EnrollmentRow) => (
    <div className="flex min-w-0 flex-col items-start gap-1">
      {statusOnly(r)}
      {funding(r)}
    </div>
  );
  const paid = (r: EnrollmentRow) => {
    const m = moneyOf.get(r.id);

    return m ? (
      <>
        <span className="font-medium">{formatPrice(m.paid)}</span>
        <MonthStates className="mt-1" states={m.month_states ?? []} />
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
    !r.donor_id &&
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
    (canChange || (instructor && r.deletable)) && (
      <Button isIconOnly aria-label={`${instructor ? "Удалить" : "Убрать"}: ${r.student_name}`} color="danger" size="sm" variant="light" onPress={() => setRemoving(r)}>
        <Icon name="trash" size={16} />
      </Button>
    );

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-default-600">
          Студентов: <b>{cohort.fill.enrolled}</b> из {cohort.fill.capacity}
          {withDonors(cohort.funding) && (
            <>
              {" "}
              · за счёт доноров: <b>{cohort.seats.donor}</b>
            </>
          )}
          {money.data && (
            <>
              {" "}
              · оплатили: <b>{money.data.payers}</b> из {money.data.enrolled}
            </>
          )}
        </p>
        <div className="flex items-center gap-2">
          <ExportButton path={`/api/v1/cohorts/${cohort.id}/enrollments/export`} />
          {canAdd && (
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
              canAdd ? (
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
          <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="w-10 px-2 py-3 text-center font-medium">№</th>
                  <th className="px-4 py-3 font-medium">Студент</th>
                  <th className="px-4 py-3 font-medium">Телефон</th>
                  <th className="px-4 py-3 font-medium">Зачислен</th>
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
                {rows.map((r, i) => (
                  <Fragment key={r.id}>
                  {i === firstExpelled && (
                    <tr className="border-y-2 border-divider bg-default-50 text-xs text-default-500">
                      <th className="px-4 py-2 text-left font-medium" colSpan={seesMoney ? 9 : 6} scope="colgroup">
                        {expelledTitle}
                      </th>
                    </tr>
                  )}
                  <tr className={clsx("border-b border-divider last:border-0 hover:bg-default-50", r.status === EXPELLED && "text-default-500")}>
                    <td className="px-2 py-3 text-center text-xs tabular-nums text-default-500">{i + 1}</td>
                    <td className="px-4 py-3 font-medium">
                      <Link className="hover:text-brand-text" href={`/students/${r.student_id}`}>
                        {r.student_name}
                      </Link>
                      {flag(r)}
                    </td>
                    <td className="px-4 py-3">{phone(r)}</td>
                    <td className="px-4 py-1">{enrolled(r)}</td>
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
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <ul data-rows className="space-y-3 md:hidden">
            {rows.map((r, i) => (
              <Fragment key={r.id}>
              {i === firstExpelled && (
                <li className="border-t-2 border-divider px-1 pt-3 text-xs font-medium text-default-500">{expelledTitle}</li>
              )}
              <li className={clsx("rounded-2xl bg-content1 p-4", r.status === EXPELLED && "text-default-500")}>
                <div className="flex items-start justify-between gap-2">
                  <Link className="min-w-0 truncate font-medium" href={`/students/${r.student_id}`}>
                    <span className="mr-2 text-xs font-normal tabular-nums text-default-500">{i + 1}.</span>
                    {r.student_name}
                  </Link>
                  {trash(r)}
                </div>
                {flag(r)}
                <div className="mt-1 text-sm">{phone(r)}</div>
                <div className="text-sm text-default-600">Зачислен {enrolled(r)}</div>
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
              </Fragment>
            ))}
          </ul>
        </>
      </QueryState>

      {dating && (
        <EnrollDateModal
          cohortStart={cohort.start_date}
          enrollment={{ ...dating, enrolled_on: enrolledOn(dating) }}
          onClose={() => setDating(null)}
        />
      )}
      {paying && <PaymentFormModal enrollmentId={paying} payment={null} onClose={() => setPaying(null)} />}
      {enrolling &&
        (instructor ? (
          <NewStudentModal cohortCode={cohort.code} cohortId={cohort.id} onClose={() => setEnrolling(false)} />
        ) : (
          <EnrollModal cohort={cohort} onClose={() => setEnrolling(false)} />
        ))}
      {removing && (
        <ConfirmModal
          confirmLabel={instructor ? "Удалить" : "Убрать"}
          danger
          isLoading={remove.isPending}
          isOpen
          title={instructor ? "Удалить студента" : "Убрать студента из потока"}
          onClose={() => setRemoving(null)}
          onConfirm={() => confirm()}
        >
          {instructor
            ? `${removing.student_name} будет удалён из потока ${cohort.code}. Если он больше нигде не учится, его карточка тоже удалится.`
            : `${removing.student_name} будет убран из потока ${cohort.code}. Сам студент останется в списке студентов.`}
        </ConfirmModal>
      )}
    </>
  );
}
