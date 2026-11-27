"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { AppModal } from "@/components/AppModal";
import { DateField } from "@/components/DateField";
import { LoadingButton } from "@/components/LoadingButton";
import { useRefreshEducation } from "@/hooks/education";
import { useRefreshAttendance } from "@/hooks/attendance";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { api } from "@/lib/api";
import { fullDate, todayIso } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

/** One enrollment day for the students ticked in the cohort list (cohort start .. today). */
export function BulkEnrollDateModal({
  cohortId,
  cohortStart,
  ids,
  onDone,
  onClose,
}: {
  cohortId: string;
  cohortStart?: string | null;
  ids: string[];
  onDone: () => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const refreshEducation = useRefreshEducation();
  const refreshAttendance = useRefreshAttendance();
  const today = todayIso();
  const [day, setDay] = useState(today);
  const valid = !!day && day <= today && (!cohortStart || day >= cohortStart);

  const save = useMutation({
    mutationFn: () =>
      api(`/api/v1/cohorts/${cohortId}/enrollments/enrolled-date`, {
        method: "POST",
        body: { enrollment_ids: ids, enrolled_on: day },
      }),
    onSuccess: () => {
      void refreshEducation();
      void refreshAttendance();
      void queryClient.invalidateQueries({ queryKey: ["lesson-attendance"] });
      void queryClient.invalidateQueries({ queryKey: ["cohort-payments"] });
      notify(`Дата зачисления ${fullDate(day)}: ${ids.length}`);
      onDone();
    },
    onError: () => void refreshEducation(),
  });
  const fe = useFieldErrors(save.error, ["enrolled_on"]);
  const submit = useSubmit(() => save.mutateAsync(), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={save.isPending} onPress={() => submit()}>
            Сохранить
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title="Дата зачисления"
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        <p className="text-sm text-default-600">Выбрано студентов: {ids.length}. Одна дата для всех. Уроки до неё нельзя отметить.</p>
        <DateField
          isRequired
          description={cohortStart ? `С ${fullDate(cohortStart)} (начало потока) по сегодня` : undefined}
          label="Дата зачисления"
          max={today}
          min={cohortStart ?? undefined}
          value={day}
          {...fe.field("enrolled_on", setDay)}
        />
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
    </AppModal>
  );
}
