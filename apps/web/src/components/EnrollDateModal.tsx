"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { AppModal } from "./AppModal";
import { DateField } from "./DateField";
import { LoadingButton } from "./LoadingButton";

import { useRefreshEducation } from "@/hooks/education";
import { useRefreshAttendance } from "@/hooks/attendance";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { api, isApiError } from "@/lib/api";
import { dayMonth, formatPrice, fullDate, todayIso } from "@/lib/education";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";

export type DatedEnrollment = { id: string; version: number; student_name: string; enrolled_on: string };

type Preview = { enrolled_on: string; first_mark: string | null; debt: { before: string; after: string } | null };

/**
 * Move the day a student was enrolled (cohort start .. today). From a locked journal cell it comes
 * preset to that lesson's day. Back-dating can add months to the debt: who sees payments is shown
 * the change before saving.
 */
export function EnrollDateModal({
  enrollment,
  cohortStart,
  preset,
  onClose,
}: {
  enrollment: DatedEnrollment;
  cohortStart?: string | null;
  /** the lesson's day from a locked cell: the button then says «Зачислить с дд.мм» */
  preset?: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const refreshEducation = useRefreshEducation();
  const refreshAttendance = useRefreshAttendance();
  const today = todayIso();
  const [day, setDay] = useState(preset ?? enrollment.enrolled_on);
  const valid = !!day && day <= today;

  const preview = useQuery({
    queryKey: ["enrolled-on-preview", enrollment.id, day],
    queryFn: () => api<Preview>(`/api/v1/enrollments/${enrollment.id}/enrolled-on`, { params: { enrolled_on: day } }),
    enabled: valid && day !== enrollment.enrolled_on,
    retry: false,
  });

  const save = useMutation({
    mutationFn: () =>
      api(`/api/v1/enrollments/${enrollment.id}/enrolled-on`, {
        method: "PATCH",
        body: { enrolled_on: day },
        version: enrollment.version,
      }),
    onSuccess: () => {
      void refreshEducation();
      void refreshAttendance();
      void queryClient.invalidateQueries({ queryKey: ["lesson-attendance"] });
      void queryClient.invalidateQueries({ queryKey: ["cohort-payments"] });
      notify(`Дата зачисления: ${fullDate(preview.data?.enrolled_on ?? day)}`);
      onClose();
    },
    onError: (e) => {
      // somebody changed the row first: show what is there now
      if (isApiError(e) && e.code === "stale_version") {
        void refreshEducation();
        void refreshAttendance();
        notifyError(e);
        onClose();
      }
    },
  });
  const fe = useFieldErrors(save.error ?? preview.error, ["enrolled_on"]);
  const submit = useSubmit(() => save.mutateAsync(), !valid || day === enrollment.enrolled_on);
  const debt = preview.data?.debt;
  const lands = preview.data?.enrolled_on;
  const marksBlock = preview.data?.first_mark && day > enrollment.enrolled_on;

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton
            color="primary"
            isDisabled={!valid || day === enrollment.enrolled_on || !!marksBlock}
            isLoading={save.isPending}
            onPress={() => submit()}
          >
            {preset && day === preset ? `Зачислить с ${dayMonth(preset)}` : "Сохранить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title="Дата зачисления"
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        <p className="text-sm text-default-600">
          {enrollment.student_name} зачислен {fullDate(enrollment.enrolled_on)}. Уроки до этой даты нельзя отметить.
        </p>
        <DateField
          isRequired
          description={cohortStart ? `С ${fullDate(cohortStart)} (начало потока) по сегодня` : undefined}
          label="Дата зачисления"
          max={today}
          min={cohortStart ?? undefined}
          value={day}
          {...fe.field("enrolled_on", setDay)}
        />
        {lands && lands !== day && <p className="text-sm text-default-600">Раньше начала потока нельзя: будет {fullDate(lands)}.</p>}
        {marksBlock && preview.data?.first_mark && (
          <p className="text-sm text-danger" role="alert">
            Есть отметки с {fullDate(preview.data.first_mark)}: дату можно сдвинуть только до этого дня.
          </p>
        )}
        {debt && debt.before !== debt.after && (
          <p className="rounded-xl bg-warning/15 p-3 text-sm text-default-700" role="status">
            Долг изменится: было {formatPrice(debt.before)} → станет {formatPrice(debt.after)}
          </p>
        )}
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
    </AppModal>
  );
}
