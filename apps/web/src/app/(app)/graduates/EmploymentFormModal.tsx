"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { useRefreshReports } from "@/hooks/reports";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { MAX_DATE, MIN_DATE, todayIso } from "@/lib/education";
import type { EmploymentRow } from "@/lib/reports-types";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

type Values = { organization: string; position: string | null; employed_at: string };

/** Add a job for a graduate (`student`) or edit a record (`job`). The only form of employment. */
export function EmploymentFormModal({
  student,
  enrollmentId,
  job,
  onClose,
}: {
  student: { id: string; name: string };
  enrollmentId?: string | null;
  job: EmploymentRow | null;
  onClose: () => void;
}) {
  const refresh = useRefreshReports();
  const [organization, setOrganization] = useState(job?.organization ?? "");
  const [position, setPosition] = useState(job?.position ?? "");
  const [date, setDate] = useState(job?.employed_at ?? todayIso());
  const valid = organization.trim() !== "" && date !== "";
  const values: Values = { organization: organization.trim(), position: position.trim() || null, employed_at: date };
  const done = () => {
    void refresh();
    notify(job ? "Трудоустройство сохранено" : "Трудоустройство добавлено");
    onClose();
  };
  const create = useMutation({
    mutationFn: () =>
      api("/api/v1/employment", { method: "POST", body: { ...values, student_id: student.id, enrollment_id: enrollmentId ?? null } }),
    onSuccess: done,
  });
  const edit = useVersionedSave({
    record: job,
    values,
    toValues: (j): Values => ({ organization: j.organization, position: j.position, employed_at: j.employed_at }),
    apply: (v) => {
      setOrganization(v.organization);
      setPosition(v.position ?? "");
      setDate(v.employed_at);
    },
    request: (changed, version) => api(`/api/v1/employment/${job?.id}`, { method: "PATCH", body: changed, version }),
    labels: { organization: "Организация", position: "Должность", employed_at: "Дата" },
    onSaved: done,
  });
  const fe = useFieldErrors(job ? edit.failure : create.error, ["organization", "position", "employed_at"]);
  const submit = useSubmit(() => (job ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
            {job ? "Сохранить" : "Добавить"}
          </LoadingButton>
        </>
      }
      isOpen
      title={job ? "Трудоустройство" : "Новое трудоустройство"}
      onClose={onClose}
    >
      <form className="grid gap-4" onSubmit={submit}>
        <p className="text-sm text-default-600">{student.name}</p>
        <Input isRequired label="Организация" value={organization} {...fe.field("organization", setOrganization)} />
        <Input label="Должность" value={position} {...fe.field("position", setPosition)} />
        <Input isRequired label="Дата трудоустройства" max={MAX_DATE} min={MIN_DATE} type="date" value={date} {...fe.field("employed_at", setDate)} />
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
      <ConflictDialog save={edit} />
    </AppModal>
  );
}
