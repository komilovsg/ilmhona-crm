"use client";

import { useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import clsx from "clsx";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { Segmented } from "@/components/Segmented";
import { Bone } from "@/components/Skeletons";
import { SelectField } from "@/components/SelectField";
import { useRefreshMoney } from "@/hooks/money";
import { usePaymentMonth } from "@/hooks/payment-month";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { formatPrice, MAX_DATE, MIN_DATE, todayIso } from "@/lib/education";
import { amountText, methodLabel, newKey, PAYMENT_METHODS, validAmount } from "@/lib/money";
import type { EnrollmentOption, PaymentRow } from "@/lib/money-types";
import {
  defaultMonth,
  holdText,
  monthConflictText,
  monthOptionLabel,
  nextOpenMonth,
  paidCountLabel,
  paidText,
  partialAmountOk,
  statusText,
  tjs,
  type MonthStatus,
  whenText,
} from "@/lib/payment-month";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

/** One student of the picker: who, which cohort, what is owed. */
function OptionButton({
  option: o,
  selected,
  onPick,
}: {
  option: EnrollmentOption;
  selected?: boolean;
  onPick?: () => void;
}) {
  const body = (
    <>
      <span className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate font-medium">{o.student_name}</span>
        <span className="shrink-0 text-xs font-medium text-brand-text">{o.cohort_code}</span>
      </span>
      <span className="mt-0.5 block text-xs text-default-500">
        {o.course_name} · {formatPrice(o.price_month)}/мес · оплачено: {paidCountLabel(o.month_states ?? [], o.months)}
        {Number(o.debt) > 0 ? ` · долг ${formatPrice(o.debt)}` : ""}
      </span>
    </>
  );

  if (!onPick) return <div className="rounded-xl bg-content2 px-3 py-2 text-sm">{body}</div>;

  return (
    <button
      aria-pressed={selected}
      className={clsx(
        "block w-full rounded-xl px-3 py-2 text-left text-sm transition-colors",
        selected ? "bg-primary/10 ring-1 ring-primary" : "bg-content2 hover:bg-default-200",
      )}
      type="button"
      onClick={onPick}
    >
      {body}
    </button>
  );
}

function Banner({ tone, children }: { tone: "warning" | "danger" | "default"; children: ReactNode }) {
  return (
    <div
      className={clsx(
        "rounded-xl px-3 py-2 text-sm",
        tone === "danger" && "bg-danger/10 text-danger-700 dark:text-danger",
        tone === "warning" && "bg-warning/20 text-warning-700 dark:text-warning",
        tone === "default" && "bg-content2 text-default-600",
      )}
      role="status"
    >
      {children}
    </div>
  );
}

/** «Частично»: the month's price, what is entered (by whom) and what is left. */
function MonthHistory({ status: s }: { status: MonthStatus }) {
  return (
    <div className="space-y-2 rounded-xl bg-content2 px-3 py-2 text-sm">
      <div className="flex justify-between gap-2">
        <span className="text-default-500">Цена месяца</span>
        <span className="font-medium">{tjs(s.price)}</span>
      </div>
      {s.payments.length > 0 && (
        <ul aria-label="Оплаты за месяц" className="space-y-1 border-t border-divider pt-2">
          {s.payments.map((p) => (
            <li key={p.id} className="flex justify-between gap-2">
              <span className="min-w-0 text-default-600">
                {whenText(p.created_at)} · {methodLabel(p.method)} · {p.created_by ?? "импорт"} ·{" "}
                <span className={p.status === "ожидает" ? "text-warning-700 dark:text-warning" : "text-success-700 dark:text-success"}>
                  {statusText(p.status)}
                </span>
              </span>
              <span className="shrink-0 font-medium">{tjs(p.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-between gap-2 border-t border-divider pt-2">
        <span className="text-default-500">Осталось</span>
        <span className="font-semibold">{tjs(s.remaining)}</span>
      </div>
    </div>
  );
}

/**
 * Create a payment (pick the student's enrollment, the month, the amount prefilled from the cohort's
 * price) or edit a pending one. The create form carries one `idempotency_key` for its whole life:
 * a double click or a retry after a lost answer never makes a second payment.
 */
export function PaymentFormModal({
  payment,
  enrollmentId = null,
  onClose,
}: {
  payment: PaymentRow | null;
  /** Open the create form with this enrollment already chosen (the cohort's «Оплата» button). */
  enrollmentId?: string | null;
  onClose: () => void;
}) {
  const refresh = useRefreshMoney();
  const [key] = useState(newKey);
  const [q, setQ] = useState("");
  const [eid, setEid] = useState<string | null>(payment?.enrollment_id ?? enrollmentId);
  // what the user typed; until then the month and the amount follow the chosen enrollment
  const [monthChoice, setMonthChoice] = useState<number | null>(payment?.month_no ?? null);
  const [amountChoice, setAmountChoice] = useState<string | null>(payment ? amountText(payment.amount) : null);
  const [method, setMethod] = useState<string>(payment?.method ?? "наличные");
  const [paidAt, setPaidAt] = useState(payment?.paid_at ?? todayIso());
  const [note, setNote] = useState(payment?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"full" | "partial">("full");
  const creating = !payment;

  const options = useQuery({
    queryKey: ["pay-options", eid ? { enrollment: eid } : { q: q.trim() }],
    queryFn: () =>
      api<EnrollmentOption[]>("/api/v1/payments/options", {
        params: eid ? { enrollment_id: eid } : { q: q.trim() || undefined },
      }),
  });
  const option = eid ? (options.data?.find((o) => o.enrollment_id === eid) ?? null) : null;
  const fullMonths = option?.full_months ?? [];
  // a new payment starts on the first month that still takes one (null: every month is paid)
  const autoMonth = option ? defaultMonth(option.months, fullMonths) : null;
  const month = monthChoice ?? (payment ? payment.month_no : autoMonth);
  const live = usePaymentMonth(eid, month, creating && !!option && month !== null);
  const st = live.status;
  const capped = !!st && Number(st.price) > 0; // a cohort without a price has no «Полностью»
  const amount = creating
    ? st && capped && mode === "full"
      ? amountText(st.remaining)
      : (amountChoice ?? "")
    : (amountChoice ?? (payment ? amountText(payment.amount) : ""));
  const dateOk = paidAt >= MIN_DATE && paidAt <= MAX_DATE;
  const monthOk = month !== null && month >= 1 && (!option || month <= option.months);
  const allPaid = creating && !!option && month === null;
  const heldBy = st && !st.full ? st.held_by : null;
  const amountOk = validAmount(amount) && (!creating || !st || !capped || partialAmountOk(amountText(amount), st.remaining));
  const valid = creating
    ? !!eid && !!option && !!st && !st.full && !heldBy && amountOk && dateOk && monthOk
    : !!eid && validAmount(amount) && dateOk && monthOk;
  const suggestion = st?.full && option && month !== null ? nextOpenMonth(option.months, fullMonths, month) : null;

  const pick = (o: EnrollmentOption | null) => {
    setEid(o?.enrollment_id ?? null);
    setMonthChoice(null);
    setAmountChoice(null);
    setError(null);
  };
  const chooseMonth = (m: number) => {
    setMonthChoice(m);
    setAmountChoice(null);
    setError(null);
  };

  const values = { month_no: month ?? 1, amount: amountText(amount), method, paid_at: paidAt, note: note.trim() || null };
  const done = () => {
    void refresh();
    notify(payment ? "Оплата сохранена" : "Оплата добавлена");
    onClose();
  };
  const create = useMutation({
    mutationFn: () =>
      api("/api/v1/payments", {
        method: "POST",
        body: { ...values, idempotency_key: key, enrollment_id: eid, partial: capped && mode === "partial" },
      }),
    onSuccess: done,
    onError: (e) => {
      // somebody paid the month meanwhile: say who, not a generic error
      setError(monthConflictText(e) ?? messageOf(e));
      live.refresh();
      void refresh();
    },
  });
  const edit = useVersionedSave({
    record: payment,
    values,
    toValues: (p) => ({
      month_no: p.month_no,
      amount: amountText(p.amount),
      method: p.method,
      paid_at: p.paid_at,
      note: p.note ?? null,
    }),
    apply: (v) => {
      setMonthChoice(v.month_no);
      setAmountChoice(v.amount);
      setMethod(v.method);
      setPaidAt(v.paid_at);
      setNote(v.note ?? "");
    },
    request: (changed, version) => api(`/api/v1/payments/${payment?.id}`, { method: "PATCH", body: changed, version }),
    labels: { month_no: "Месяц", amount: "Сумма", method: "Способ", paid_at: "Дата", note: "Заметка" },
    show: {
      amount: (a: string) => formatPrice(a),
      method: (m: string) => methodLabel(m),
      note: (n: string | null) => n || "—",
    },
    onSaved: done,
  });
  const submit = useSubmit(() => (payment ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton
            color="primary"
            isDisabled={!valid}
            isLoading={create.isPending || edit.pending || !!heldBy}
            onPress={() => submit()}
          >
            {payment ? "Сохранить" : "Добавить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title={payment ? "Оплата" : "Новая оплата"}
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        {payment ? (
          <div className="rounded-xl bg-content2 px-3 py-2 text-sm">
            <div className="font-medium">{payment.student_name}</div>
            <div className="text-xs text-default-500">
              {payment.cohort_code} · {payment.course_name}
            </div>
          </div>
        ) : eid && option ? (
          <div className="space-y-2">
            <OptionButton option={option} />
            <button className="text-sm text-brand-text" type="button" onClick={() => pick(null)}>
              Выбрать другого студента
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <Input
              autoFocus
              isClearable
              label="Студент или поток"
              placeholder="Имя, телефон или код потока"
              startContent={<Icon name="search" size={18} />}
              value={q}
              onClear={() => setQ("")}
              onValueChange={setQ}
            />
            <div className="h-60 space-y-1.5 overflow-y-auto" role="group" aria-label="Студенты">
              {options.isPending && !options.isError && (
                <>
                  <Bone className="h-[52px] w-full rounded-xl" />
                  <Bone className="h-[52px] w-full rounded-xl" />
                  <Bone className="h-[52px] w-full rounded-xl" />
                </>
              )}
              {options.isError && (
                <p className="text-sm text-danger" role="alert">
                  Не удалось загрузить студентов.{" "}
                  <button className="underline" type="button" onClick={() => void options.refetch()}>
                    Повторить
                  </button>
                </p>
              )}
              {options.data?.length === 0 && <p className="py-6 text-center text-sm text-default-500">Студент не найден</p>}
              {options.data?.map((o) => (
                <OptionButton key={o.enrollment_id} option={o} onPick={() => pick(o)} />
              ))}
            </div>
          </div>
        )}

        {allPaid && <Banner tone="default">Все месяцы оплачены</Banner>}

        {(payment || (option && !allPaid)) && (
          <>
            {creating && capped && !st.full && (
              <Segmented
                label="Сумма оплаты"
                options={[
                  { key: "full", label: "Полностью" },
                  { key: "partial", label: "Частично" },
                ]}
                value={mode}
                onChange={(m) => {
                  setMode(m);
                  setAmountChoice(null);
                }}
              />
            )}
            {st?.full && month !== null && (
              <Banner tone="danger">
                {paidText(st)}
                {suggestion !== null && (
                  <button className="mt-1 block font-medium underline" type="button" onClick={() => chooseMonth(suggestion)}>
                    Перейти к месяцу {suggestion}
                  </button>
                )}
              </Banner>
            )}
            {heldBy && month !== null && <Banner tone="warning">{holdText(heldBy.name, month)}</Banner>}
            <div className="grid grid-cols-2 gap-3">
              {option ? (
                <SelectField
                  isRequired
                  className="col-span-2"
                  label="Месяц"
                  options={Array.from({ length: option.months }, (_, i) => {
                    const state = option.month_states?.find((s) => s.month_no === i + 1);

                    return { key: String(i + 1), label: monthOptionLabel(i + 1, state) };
                  })}
                  value={month === null ? "" : String(month)}
                  onChange={(m) => {
                    if (m) chooseMonth(Number(m));
                  }}
                />
              ) : (
                <Input
                  isRequired
                  label="Месяц"
                  min={1}
                  type="number"
                  value={String(month ?? "")}
                  onValueChange={(m) => setMonthChoice(Number(m))}
                />
              )}
              <Input
                isRequired
                className={option ? "col-span-2" : undefined}
                description={creating && st && capped && mode === "full" && Number(st.paid) > 0 ? "Остаток месяца" : undefined}
                endContent={<span className="text-xs text-default-500">TJS</span>}
                errorMessage={creating && st && capped ? `Не больше ${tjs(st.remaining)}` : undefined}
                inputMode="decimal"
                isInvalid={amount !== "" && !amountOk}
                isReadOnly={creating && capped && mode === "full"}
                label="Сумма"
                value={amount}
                onValueChange={setAmountChoice}
              />
            </div>
            {creating && st && capped && mode === "partial" && !st.full && (
              <>
                <MonthHistory status={st} />
                <button
                  className="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-brand-text"
                  type="button"
                  onClick={() => setAmountChoice(amountText(st.remaining))}
                >
                  Остаток {tjs(st.remaining)}
                </button>
              </>
            )}
            <div className="grid grid-cols-2 gap-3">
              <SelectField
                isRequired
                label="Способ"
                options={PAYMENT_METHODS.map((m) => ({ key: m.key, label: m.label }))}
                value={method}
                onChange={(m) => setMethod(m ?? "наличные")}
              />
              <Input
                isRequired
                label="Дата оплаты"
                max={MAX_DATE}
                min={MIN_DATE}
                placeholder=" "
                type="date"
                value={paidAt}
                onValueChange={setPaidAt}
              />
            </div>
            <Input label="Заметка" maxLength={500} value={note} onValueChange={setNote} />
          </>
        )}
        {(error ?? edit.error) && !st?.full && (
          <p className="text-sm text-danger" role="alert">
            {error ?? edit.error}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}
