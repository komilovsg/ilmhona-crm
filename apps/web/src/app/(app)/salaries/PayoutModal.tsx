"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConfirmModal } from "@/components/ConfirmModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { SelectField } from "@/components/SelectField";
import { useRefreshMoney } from "@/hooks/money";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { formatPrice, MAX_DATE, MIN_DATE, todayIso } from "@/lib/education";
import { amountText, methodLabel, monthLabel, PAYMENT_METHODS, validAmount } from "@/lib/money";
import type { SalaryRow } from "@/lib/money-types";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";

/**
 * «Отметить выплату»: the payout of one cohort-month (the amount defaults to the rate), or the edit
 * of a payout already made (with the delete). One payout per instructor, cohort and month: a second
 * one is refused by the API.
 */
export function PayoutModal({ row, onClose }: { row: SalaryRow; onClose: () => void }) {
  const refresh = useRefreshMoney();
  const payout = row.payout;
  const [amount, setAmount] = useState(amountText(payout?.amount ?? row.rate));
  const [method, setMethod] = useState<string>(payout?.method ?? "наличные");
  const [paidAt, setPaidAt] = useState(payout?.paid_at ?? todayIso());
  const [note, setNote] = useState(payout?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const valid = validAmount(amount) && paidAt >= MIN_DATE && paidAt <= MAX_DATE;

  const values = { amount: amountText(amount), method, paid_at: paidAt, note: note.trim() || null };
  const done = () => {
    void refresh();
    notify(payout ? "Выплата сохранена" : "Выплата отмечена");
    onClose();
  };
  const create = useMutation({
    mutationFn: () =>
      api("/api/v1/payouts", { method: "POST", body: { ...values, cohort_id: row.cohort_id, period: row.period } }),
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: payout,
    values,
    toValues: (p) => ({ amount: amountText(p.amount), method: p.method, paid_at: p.paid_at, note: p.note ?? null }),
    apply: (v) => {
      setAmount(v.amount);
      setMethod(v.method);
      setPaidAt(v.paid_at);
      setNote(v.note ?? "");
    },
    request: (changed, version) => api(`/api/v1/payouts/${payout?.id}`, { method: "PATCH", body: changed, version }),
    labels: { amount: "Сумма", method: "Способ", paid_at: "Дата", note: "Заметка" },
    show: { amount: (a: string) => formatPrice(a), method: (m: string) => methodLabel(m), note: (n: string | null) => n || "—" },
    onSaved: done,
  });
  const remove = useMutation({
    mutationFn: () => api(`/api/v1/payouts/${payout?.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      notify("Выплата удалена");
      onClose();
    },
    onError: (e) => {
      setDeleting(false);
      notifyError(e);
    },
  });
  const submit = useSubmit(() => (payout ? edit.save(values) : create.mutateAsync()), !valid);
  const confirmDelete = useSubmit(() => remove.mutateAsync());

  return (
    <>
      <AppModal
        footer={
          <>
            {payout && (
              <Button className="sm:mr-auto" color="danger" variant="light" onPress={() => setDeleting(true)}>
                Удалить выплату
              </Button>
            )}
            <Button variant="light" onPress={onClose}>
              Отмена
            </Button>
            <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
              {payout ? "Сохранить" : "Отметить"}
            </LoadingButton>
          </>
        }
        isOpen
        size="md"
        title={payout ? "Выплата" : "Отметить выплату"}
        onClose={onClose}
      >
        <form className="space-y-4" onSubmit={submit}>
          <div className="rounded-xl bg-content2 px-3 py-2 text-sm">
            <div className="font-medium">{row.instructor_name}</div>
            <div className="text-xs text-default-500">
              {row.cohort_code} · {row.course_name} · {monthLabel(row.period)} · ставка {formatPrice(row.rate)}
            </div>
          </div>
          <Input
            autoFocus
            isRequired
            endContent={<span className="text-xs text-default-500">TJS</span>}
            inputMode="decimal"
            isInvalid={amount !== "" && !validAmount(amount)}
            label="Сумма"
            value={amount}
            onValueChange={setAmount}
          />
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
              label="Дата выплаты"
              max={MAX_DATE}
              min={MIN_DATE}
              placeholder=" "
              type="date"
              value={paidAt}
              onValueChange={setPaidAt}
            />
          </div>
          <Input label="Заметка" maxLength={500} value={note} onValueChange={setNote} />
          {(error ?? edit.error) && (
            <p className="text-sm text-danger" role="alert">
              {error ?? edit.error}
            </p>
          )}
        </form>
        <ConflictDialog save={edit} />
      </AppModal>
      {deleting && (
        <ConfirmModal
          confirmLabel="Удалить"
          danger
          isLoading={remove.isPending}
          isOpen
          title="Удалить выплату"
          onClose={() => setDeleting(false)}
          onConfirm={() => confirmDelete()}
        >
          Выплата {row.instructor_name} за {monthLabel(row.period)} будет удалена, расходы на зарплату и прибыль пересчитаются.
        </ConfirmModal>
      )}
    </>
  );
}
