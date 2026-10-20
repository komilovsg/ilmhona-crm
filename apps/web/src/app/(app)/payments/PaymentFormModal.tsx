"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import clsx from "clsx";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { Bone } from "@/components/Skeletons";
import { SelectField } from "@/components/SelectField";
import { useRefreshMoney } from "@/hooks/money";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { formatPrice, MAX_DATE, MIN_DATE, todayIso } from "@/lib/education";
import { amountText, methodLabel, newKey, PAYMENT_METHODS, paidMonthsLabel, validAmount } from "@/lib/money";
import type { EnrollmentOption, PaymentRow } from "@/lib/money-types";
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
      <span className="mt-0.5 block truncate text-xs text-default-500">
        {o.course_name} · {formatPrice(o.price_month)}/мес · оплачено: {paidMonthsLabel(o.paid_months, o.months)}
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

  const options = useQuery({
    queryKey: ["pay-options", eid ? { enrollment: eid } : { q: q.trim() }],
    queryFn: () =>
      api<EnrollmentOption[]>("/api/v1/payments/options", {
        params: eid ? { enrollment_id: eid } : { q: q.trim() || undefined },
      }),
  });
  const option = eid ? (options.data?.find((o) => o.enrollment_id === eid) ?? null) : null;
  const month = monthChoice ?? option?.next_month ?? 1;
  const amount = amountChoice ?? (option ? amountText(option.price_month) : "");
  const dateOk = paidAt >= MIN_DATE && paidAt <= MAX_DATE;
  const monthOk = month >= 1 && (!option || month <= option.months);
  const valid = !!eid && validAmount(amount) && dateOk && monthOk && (!!payment || !!option);

  const pick = (o: EnrollmentOption | null) => {
    setEid(o?.enrollment_id ?? null);
    setMonthChoice(null);
    setAmountChoice(null);
  };

  const values = { month_no: month, amount: amountText(amount), method, paid_at: paidAt, note: note.trim() || null };
  const done = () => {
    void refresh();
    notify(payment ? "Оплата сохранена" : "Оплата добавлена");
    onClose();
  };
  const create = useMutation({
    mutationFn: () =>
      api("/api/v1/payments", {
        method: "POST",
        body: { ...values, idempotency_key: key, enrollment_id: eid },
      }),
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
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
          <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
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

        {(payment || option) && (
          <>
            <div className="grid grid-cols-2 gap-3">
              {option ? (
                <SelectField
                  isRequired
                  label="Месяц"
                  options={Array.from({ length: option.months }, (_, i) => ({
                    key: String(i + 1),
                    label: `${i + 1}-й${option.paid_months.includes(i + 1) ? " · оплачен" : ""}`,
                  }))}
                  value={String(month)}
                  onChange={(m) => setMonthChoice(Number(m))}
                />
              ) : (
                <Input
                  isRequired
                  label="Месяц"
                  min={1}
                  type="number"
                  value={String(month)}
                  onValueChange={(m) => setMonthChoice(Number(m))}
                />
              )}
              <Input
                isRequired
                endContent={<span className="text-xs text-default-500">TJS</span>}
                inputMode="decimal"
                isInvalid={amount !== "" && !validAmount(amount)}
                label="Сумма"
                value={amount}
                onValueChange={setAmountChoice}
              />
            </div>
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
        {(error ?? edit.error) && (
          <p className="text-sm text-danger" role="alert">
            {error ?? edit.error}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}
