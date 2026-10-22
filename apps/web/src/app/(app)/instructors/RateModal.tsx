"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { useRefreshMoney } from "@/hooks/money";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { formatPrice } from "@/lib/education";
import { amountText, validRate } from "@/lib/money";
import type { Money } from "@/lib/money-types";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

/** What a rate form edits: the record as loaded (its `version`) and which field holds the rate. */
export type RateRecord = { version: number } & Record<string, unknown>;

/**
 * Edit a rate (the instructor's default, or one cohort's rate): a number ≥ 0, saved with the version
 * the screen loaded (#25) — a conflict opens the shared dialog.
 */
export function RateModal({
  title,
  hint,
  record,
  field,
  request,
  onClose,
}: {
  title: string;
  hint?: string;
  record: RateRecord;
  /** `default_rate` for an instructor, `instructor_rate` for a cohort (also what a 409 brings back). */
  field: string;
  request: (rate: string, version: number) => Promise<unknown>;
  onClose: () => void;
}) {
  const refresh = useRefreshMoney();
  const [text, setText] = useState(amountText(record[field] as Money));
  const valid = validRate(text);
  const values = { rate: amountText(text) };

  const save = useVersionedSave({
    record,
    values,
    toValues: (r) => ({ rate: amountText(r[field] as Money) }),
    apply: (v) => setText(v.rate),
    request: (changed, version) => request(changed.rate ?? values.rate, version),
    labels: { rate: "Ставка за месяц" },
    show: { rate: (r: string) => formatPrice(r) },
    onSaved: () => {
      void refresh();
      notify("Ставка сохранена");
      onClose();
    },
  });
  const fe = useFieldErrors(save.failure, [field]);
  const submit = useSubmit(() => save.save(values), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={save.pending} onPress={() => submit()}>
            Сохранить
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title={title}
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        <Input
          autoFocus
          isRequired
          endContent={<span className="text-xs text-default-500">TJS</span>}
          inputMode="decimal"
          errorMessage={fe.hint(field).errorMessage}
          isInvalid={(text !== "" && !valid) || fe.hint(field).isInvalid}
          label="Ставка за месяц"
          value={text}
          onValueChange={(v) => {
            fe.clear(field);
            setText(v);
          }}
        />
        {hint && <p className="text-sm text-default-500">{hint}</p>}
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
      <ConflictDialog save={save} />
    </AppModal>
  );
}
