"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useMutation, keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";
import { SheetHandle } from "@/components/SheetHandle";
import { Input } from "@heroui/input";


import { ConfirmModal } from "@/components/ConfirmModal";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { MonthStates } from "@/components/MonthStates";
import { LoadingButton } from "@/components/LoadingButton";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { RowMenu } from "@/components/RowMenu";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { StatCards, StatCardsSkeleton } from "@/components/StatCards";
import { useCanPay, useRefreshMoney, useSeesPayments } from "@/hooks/money";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatPrice, fullDate, todayIso } from "@/lib/education";
import { telHref } from "@/lib/format";
import { methodLabel, monthOf, monthOptions, PAYMENT_METHODS, PAYMENT_STATUSES, paymentTone } from "@/lib/money";
import type { DebtorRow, DebtorsPage, PaymentRow, PaymentsPage } from "@/lib/money-types";
import { dueText } from "@/lib/payment-month";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import { useOverlayMotion } from "@/lib/motion";

const PaymentFormModal = dynamic(() => import("./PaymentFormModal").then((m) => m.PaymentFormModal));

const PAGE_SIZE = 25;
type Tab = "payments" | "debtors";
type Filters = { q: string; status: string | null; method: string | null; month: string | null; branch: string | null };
const NO_FILTERS: Filters = { q: "", status: null, method: null, month: null, branch: null };

function FilterFields({ filters, set, debtors }: { filters: Filters; set: (f: Filters) => void; debtors: boolean }) {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();

  return (
    <>
      {!debtors && (
        <>
          <SelectField
            allLabel="Любой статус"
            className="md:w-44"
            label="Статус"
            options={PAYMENT_STATUSES.map((s) => ({ key: s, label: s }))}
            value={filters.status}
            onChange={(status) => set({ ...filters, status })}
          />
          <SelectField
            allLabel="Любой способ"
            className="md:w-44"
            label="Способ"
            options={PAYMENT_METHODS.map((m) => ({ key: m.key, label: m.label }))}
            value={filters.method}
            onChange={(method) => set({ ...filters, method })}
          />
          <SelectField
            allLabel="Любой месяц"
            className="md:w-48"
            label="Месяц оплаты"
            options={monthOptions(monthOf(todayIso()), 12, 0)}
            value={filters.month}
            onChange={(month) => set({ ...filters, month })}
          />
        </>
      )}
      {!me?.branch && (
        <SelectField
          allLabel="Все филиалы"
          className="md:w-48"
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={filters.branch}
          onChange={(branch) => set({ ...filters, branch })}
        />
      )}
    </>
  );
}

function StatusChip({ status }: { status: string }) {
  return (
    <Chip color={paymentTone(status)} size="sm" variant="flat">
      {status}
    </Chip>
  );
}

function Phone({ value }: { value: string | null }) {
  return value ? (
    <a className="text-brand-text" href={telHref(value)}>
      {value}
    </a>
  ) : null;
}

type Actions = {
  busy: string | null;
  confirm: (p: PaymentRow) => void;
  unconfirm: (p: PaymentRow) => void;
  edit: (p: PaymentRow) => void;
  remove: (p: PaymentRow) => void;
};

function RowActions({ p, canPay, a }: { p: PaymentRow; canPay: boolean; a: Actions }) {
  if (!canPay) return null;
  const pending = p.status === "ожидает";

  return (
    <div className="flex items-center justify-end gap-1">
      {pending && (
        <LoadingButton
          color="primary"
          isLoading={a.busy === p.id}
          size="sm"
          startContent={<Icon name="check" size={16} />}
          variant="flat"
          onPress={() => a.confirm(p)}
        >
          Подтвердить
        </LoadingButton>
      )}
      <RowMenu
        actions={
          pending
            ? [
                { key: "edit", label: "Изменить", icon: "edit" },
                { key: "delete", label: "Удалить", icon: "trash", danger: true },
              ]
            : [{ key: "unconfirm", label: "Снять подтверждение", icon: "ban" }]
        }
        label={`Действия с оплатой: ${p.student_name}`}
        onAction={(k) => (k === "edit" ? a.edit(p) : k === "delete" ? a.remove(p) : a.unconfirm(p))}
      />
    </div>
  );
}

function PaymentsList({ rows, canPay, a }: { rows: PaymentRow[]; canPay: boolean; a: Actions }) {
  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Дата</th>
              <th className="px-4 py-3 font-medium">Студент</th>
              <th className="px-4 py-3 font-medium">Поток</th>
              <th className="px-4 py-3 font-medium">Месяц</th>
              <th className="px-4 py-3 font-medium">Сумма</th>
              <th className="px-4 py-3 font-medium">Способ</th>
              <th className="px-4 py-3 font-medium">Статус</th>
              <th className="px-4 py-3 text-right font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="whitespace-nowrap px-4 py-3 text-default-600">{fullDate(p.paid_at)}</td>
                <td className="px-4 py-3 font-medium">
                  <Link className="hover:text-brand-text" href={`/students/${p.student_id}`}>
                    {p.student_name}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <Link className="text-brand-text" href={`/cohorts/${p.cohort_id}`}>
                    {p.cohort_code}
                  </Link>
                </td>
                <td className="px-4 py-3">{p.month_no}</td>
                <td className="whitespace-nowrap px-4 py-3 font-medium">{formatPrice(p.amount)}</td>
                <td className="px-4 py-3">{methodLabel(p.method)}</td>
                <td className="px-4 py-3">
                  <StatusChip status={p.status} />
                </td>
                <td className="px-3 py-2">
                  <RowActions a={a} canPay={canPay} p={p} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-rows className="space-y-3 md:hidden">
        {rows.map((p) => (
          <li key={p.id} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-start justify-between gap-2">
              <Link className="min-w-0 truncate font-medium" href={`/students/${p.student_id}`}>
                {p.student_name}
              </Link>
              <StatusChip status={p.status} />
            </div>
            <div className="mt-1 text-sm text-default-500">
              <Link className="text-brand-text" href={`/cohorts/${p.cohort_id}`}>
                {p.cohort_code}
              </Link>{" "}
              · месяц {p.month_no} · {methodLabel(p.method)}
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <div>
                <div className="font-semibold">{formatPrice(p.amount)}</div>
                <div className="text-xs text-default-500">{fullDate(p.paid_at)}</div>
              </div>
              <RowActions a={a} canPay={canPay} p={p} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function DebtorsList({ rows, canPay, onPay }: { rows: DebtorRow[]; canPay: boolean; onPay: (d: DebtorRow) => void }) {
  const payButton = (d: DebtorRow) =>
    canPay && (
      <Button color="primary" size="sm" startContent={<Icon name="payments" size={16} />} variant="flat" onPress={() => onPay(d)}>
        Оплата
      </Button>
    );

  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="px-4 py-3 font-medium">Студент</th>
              <th className="px-4 py-3 font-medium">Поток</th>
              <th className="px-4 py-3 font-medium">Месяцы</th>
              <th className="px-4 py-3 font-medium">Должен был</th>
              <th className="px-4 py-3 font-medium">Оплачено</th>
              <th className="px-4 py-3 font-medium">Долг</th>
              <th className="px-4 py-3 text-right font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.enrollment_id} className="border-b border-divider last:border-0 hover:bg-default-50">
                <td className="px-4 py-3 font-medium">
                  <Link className="hover:text-brand-text" href={`/students/${d.student_id}`}>
                    {d.student_name}
                  </Link>
                  <div className="text-xs font-normal">
                    <Phone value={d.phone} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Link className="text-brand-text" href={`/cohorts/${d.cohort_id}`}>
                    {d.cohort_code}
                  </Link>
                  <div className="text-xs text-default-500">{d.course_name}</div>
                </td>
                <td className="px-4 py-3">
                  <MonthStates states={d.month_states ?? []} />
                  {d.due_months?.length > 0 && <div className="mt-0.5 text-xs text-danger">Осталось: {dueText(d.due_months)}</div>}
                </td>
                <td className="whitespace-nowrap px-4 py-3">{formatPrice(d.expected)}</td>
                <td className="whitespace-nowrap px-4 py-3">{formatPrice(d.paid)}</td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-danger">{formatPrice(d.debt)}</td>
                <td className="px-3 py-2 text-right">{payButton(d)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul data-rows className="space-y-3 md:hidden">
        {rows.map((d) => (
          <li key={d.enrollment_id} className="rounded-2xl bg-content1 p-4">
            <div className="flex items-start justify-between gap-2">
              <Link className="min-w-0 truncate font-medium" href={`/students/${d.student_id}`}>
                {d.student_name}
              </Link>
              <span className="shrink-0 font-semibold text-danger">{formatPrice(d.debt)}</span>
            </div>
            <div className="mt-1 text-sm text-default-500">
              {d.cohort_code}
            </div>
            <MonthStates className="mt-1" states={d.month_states ?? []} />
            {d.due_months?.length > 0 && <div className="mt-0.5 text-xs text-danger">Осталось: {dueText(d.due_months)}</div>}
            <div className="mt-1 text-sm">
              <Phone value={d.phone} />
            </div>
            <div className="mt-2 flex justify-end">{payButton(d)}</div>
          </li>
        ))}
      </ul>
    </>
  );
}

export default function PaymentsPage() {
  const overlayMotion = useOverlayMotion();
  const sees = useSeesPayments();
  const canPay = useCanPay();
  const refresh = useRefreshMoney();
  const [tab, setTab] = useState<Tab>("payments");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [form, setForm] = useState<{ payment: PaymentRow | null; enrollmentId: string | null } | null>(null);
  const [removing, setRemoving] = useState<PaymentRow | null>(null);
  const debtors = tab === "debtors";

  const list = useQuery({
    queryKey: ["payments", filters, page],
    queryFn: () =>
      api<PaymentsPage>("/api/v1/payments", {
        params: {
          q: filters.q.trim() || undefined,
          status: filters.status ?? undefined,
          method: filters.method ?? undefined,
          month: filters.month ?? undefined,
          branch_id: filters.branch ?? undefined,
          page: String(page),
          page_size: String(PAGE_SIZE),
        },
      }),
    placeholderData: keepPreviousData,
    enabled: sees && !debtors,
  });
  const owed = useQuery({
    queryKey: ["debtors", filters.q, filters.branch, page],
    queryFn: () =>
      api<DebtorsPage>("/api/v1/payments/debtors", {
        params: {
          q: filters.q.trim() || undefined,
          branch_id: filters.branch ?? undefined,
          page: String(page),
          page_size: String(PAGE_SIZE),
        },
      }),
    placeholderData: keepPreviousData,
    enabled: sees && debtors,
  });

  const [busy, setBusy] = useState<string | null>(null);
  const setStatus = useMutation({
    mutationFn: ({ p, to }: { p: PaymentRow; to: "confirm" | "unconfirm" }) => {
      setBusy(p.id);

      return api(`/api/v1/payments/${p.id}/${to}`, { method: "POST", version: p.version });
    },
    onSuccess: (_, { to }) => notify(to === "confirm" ? "Оплата подтверждена" : "Подтверждение снято"),
    onError: notifyError,
    onSettled: () => {
      setBusy(null);
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (p: PaymentRow) => api(`/api/v1/payments/${p.id}`, { method: "DELETE" }),
    onSuccess: () => {
      notify("Оплата удалена");
      setRemoving(null);
    },
    onError: (e) => {
      setRemoving(null);
      notifyError(e);
    },
    onSettled: () => void refresh(),
  });
  const confirmRemove = useSubmit(() => (removing ? remove.mutateAsync(removing) : Promise.resolve()));

  if (!sees) return <p className="rounded-xl bg-content1 p-6 text-default-600">У вас нет доступа к этому разделу.</p>;

  const set = (next: Filters) => {
    setFilters(next);
    setPage(1);
  };
  const actions: Actions = {
    busy,
    confirm: (p) => setStatus.mutate({ p, to: "confirm" }),
    unconfirm: (p) => setStatus.mutate({ p, to: "unconfirm" }),
    edit: (p) => setForm({ payment: p, enrollmentId: null }),
    remove: setRemoving,
  };
  const activeFilters = debtors
    ? [filters.branch].filter(Boolean).length
    : [filters.status, filters.method, filters.month, filters.branch].filter(Boolean).length;
  const filtered = activeFilters > 0 || !!filters.q.trim();
  const summary = list.data?.summary;
  const addButton = canPay && (
    <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setForm({ payment: null, enrollmentId: null })}>
      Оплата
    </Button>
  );

  return (
    <>
      <PageHeader
        actions={
          <>
            <ExportButton
              params={debtors ? { q: filters.q.trim(), branch_id: filters.branch } : {
                q: filters.q.trim(),
                status: filters.status,
                method: filters.method,
                month: filters.month,
                branch_id: filters.branch,
              }}
              path={debtors ? "/api/v1/payments/debtors/export" : "/api/v1/payments/export"}
            />
            {addButton}
          </>
        }
        title="Оплаты"
      />

      {debtors ? (
        owed.data ? (
          <StatCards
            stats={[
              { label: "Должников", value: String(owed.data.total) },
              { label: "Общий долг", value: formatPrice(owed.data.total_debt), tone: Number(owed.data.total_debt) > 0 ? "danger" : "default" },
            ]}
          />
        ) : (
          <StatCardsSkeleton count={2} />
        )
      ) : summary ? (
        <StatCards
          stats={[
            { label: "Подтверждено", value: formatPrice(summary.confirmed), hint: `оплат: ${summary.confirmed_count}`, tone: "success" },
            { label: "Ожидает подтверждения", value: formatPrice(summary.pending), hint: `оплат: ${summary.pending_count}`, tone: "warning" },
            { label: "Транзакций", value: String(summary.count) },
          ]}
        />
      ) : (
        <StatCardsSkeleton count={3} />
      )}

      <Segmented
        className="mb-4"
        label="Раздел оплат"
        options={[
          { key: "payments", label: "Оплаты" },
          { key: "debtors", label: "Должники" },
        ]}
        value={tab}
        onChange={(t) => {
          setTab(t);
          setPage(1);
        }}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          className="flex-1 md:max-w-xs md:flex-none"
          isClearable
          placeholder="Поиск: студент, телефон, поток"
          startContent={<Icon name="search" size={18} />}
          value={filters.q}
          onClear={() => set({ ...filters, q: "" })}
          onValueChange={(q) => set({ ...filters, q })}
        />
        <div className="hidden gap-3 md:flex">
          <FilterFields debtors={debtors} filters={filters} set={set} />
        </div>
        <Button className="md:hidden" startContent={<Icon name="filter" size={18} />} variant="flat" onPress={() => setFiltersOpen(true)}>
          Фильтры{activeFilters ? ` · ${activeFilters}` : ""}
        </Button>
      </div>

      {debtors ? (
        <QueryState
          empty={
            <EmptyState
              hint={filtered ? "Измените поиск или фильтры." : undefined}
              title={filtered ? "Должников не найдено" : "Должников нет"}
            />
          }
          isEmpty={(d) => d.items.length === 0}
          query={owed}
          skeleton={<ListSkeleton cols={7} />}
        >
          {(d) => (
            <>
              <DebtorsList canPay={canPay} rows={d.items} onPay={(x) => setForm({ payment: null, enrollmentId: x.enrollment_id })} />
              <Pager page={page} pageSize={PAGE_SIZE} total={d.total} onChange={setPage} />
            </>
          )}
        </QueryState>
      ) : (
        <QueryState
          empty={
            <EmptyState
              action={canPay && !filtered ? addButton : undefined}
              hint={filtered ? "Измените поиск или фильтры." : undefined}
              title={filtered ? "Оплат не найдено" : "Оплат пока нет"}
            />
          }
          isEmpty={(d) => d.items.length === 0}
          query={list}
          skeleton={<ListSkeleton cols={8} />}
        >
          {(d) => (
            <>
              <PaymentsList a={actions} canPay={canPay} rows={d.items} />
              <Pager page={page} pageSize={PAGE_SIZE} total={d.total} onChange={setPage} />
            </>
          )}
        </QueryState>
      )}

      <Drawer isOpen={filtersOpen} motionProps={overlayMotion} placement="bottom" onOpenChange={setFiltersOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <SheetHandle onBackdrop={close} onClose={close} />
              <DrawerHeader>Фильтры</DrawerHeader>
              <DrawerBody className="gap-3">
                <FilterFields debtors={debtors} filters={filters} set={set} />
              </DrawerBody>
              <DrawerFooter>
                <Button variant="light" onPress={() => set({ ...NO_FILTERS, q: filters.q })}>
                  Сбросить
                </Button>
                <Button color="primary" onPress={close}>
                  Показать
                </Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {form && <PaymentFormModal enrollmentId={form.enrollmentId} payment={form.payment} onClose={() => setForm(null)} />}
      {removing && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Удалить оплату"
          onClose={() => setRemoving(null)}
          onConfirm={() => confirmRemove()}
        >
          Оплата {removing.student_name} за месяц {removing.month_no} на {formatPrice(removing.amount)} будет удалена. Подтверждённую
          оплату удалить нельзя.
        </ConfirmModal>
      )}
    </>
  );
}
