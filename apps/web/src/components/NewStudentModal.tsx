"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "./AppModal";
import { DateField } from "./DateField";
import { LoadingButton } from "./LoadingButton";
import { Segmented } from "./Segmented";

import { OverCapacityNotice } from "./OverCapacityNotice";
import { SelectField } from "./SelectField";

import { useRefreshEducation } from "@/hooks/education";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { api } from "@/lib/api";
import { overToast, wouldExceed } from "@/lib/capacity";
import { todayIso } from "@/lib/education";
import { payerBody, payerOptions, priced } from "@/lib/funding";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { CohortRow, EnrollmentRow } from "@/lib/types";

type Gender = "none" | "male" | "female";

const GENDERS: { key: Gender; label: string }[] = [
  { key: "none", label: "Не указан" },
  { key: "male", label: "М" },
  { key: "female", label: "Ж" },
];

/**
 * The instructor's quick form: a new student straight into their own cohort, mostly from a phone during a
 * lesson. «Сохранить и добавить ещё» keeps the form open for the next one.
 */
export function NewStudentModal({
  cohortId,
  cohortCode,
  onSaved,
  onClose,
}: {
  cohortId: string;
  cohortCode: string;
  onSaved?: (row: EnrollmentRow) => void;
  onClose: () => void;
}) {
  const refresh = useRefreshEducation();
  // the live fill: refetched after every save, so «сохранить и добавить ещё» keeps the warning right
  const cohort = useQuery({ queryKey: ["cohort", cohortId], queryFn: () => api<CohortRow>(`/api/v1/cohorts/${cohortId}`) });
  const fill = cohort.data?.fill;
  const exceeds = wouldExceed(fill);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [gender, setGender] = useState<Gender>("none");
  const nameRef = useRef<HTMLInputElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  const again = useRef(false);
  // who pays for the student: «платит сам», «не платит» (a paid or mixed cohort) or one of this
  // cohort's donors (from its own card); a single donor of a «донор» cohort is set by the server,
  // so the field is not shown then.
  const funding = cohort.data?.funding;
  const donors = (cohort.data?.donors ?? []).filter((d) => !d.archived);
  const payers = funding ? payerOptions(funding, donors) : [];
  const pickDonor = payers.length > 0 && !(funding === "донор" && donors.length === 1);
  const donorMissing = funding === "донор" && donors.length > 1;
  const [donorId, setDonorId] = useState<string | null>(null);
  // a running cohort: the day the student really started (kept for «добавить ещё»)
  const today = todayIso();
  const start = cohort.data?.start_date;
  const running = !!start && start < today;
  const [enrolledOn, setEnrolledOn] = useState(today);

  const save = useMutation({
    mutationFn: () =>
      api<EnrollmentRow>(`/api/v1/cohorts/${cohortId}/enrollments`, {
        method: "POST",
        body: {
          new_student: { full_name: name, phone: phone.trim() || null, gender: gender === "none" ? null : gender },
          ...(pickDonor ? payerBody(donorId) : {}),
          ...(running && enrolledOn && enrolledOn !== today ? { enrolled_on: enrolledOn } : {}),
        },
      }),
    onSuccess: (row) => {
      void refresh();
      onSaved?.(row);
      notify(`Студент добавлен${overToast(row.over_capacity)}`);
      if (!again.current) return onClose();
      setName("");
      setPhone("");
      setGender("none");
      save.reset();
      nameRef.current?.focus();
    },
  });
  const fe = useFieldErrors(save.error, ["full_name", "phone", "gender", "donor_id", "not_paying", "enrolled_on"]);
  const valid = !!name.trim() && !(donorMissing && !donorId);
  const submit = useSubmit(() => save.mutateAsync(), !valid);
  const run = (more: boolean) => {
    again.current = more;
    submit();
  };

  return (
    <AppModal
      footer={
        <>
          <Button className="max-sm:hidden" variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button isDisabled={!valid || save.isPending} color="primary" variant="flat" onPress={() => run(true)}>
            {exceeds ? "Всё равно и ещё" : "Сохранить и добавить ещё"}
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={save.isPending} onPress={() => run(false)}>
            {exceeds ? "Записать всё равно" : "Сохранить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title={`Новый студент в ${cohortCode}`}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          run(false);
        }}
      >
        <Input
          ref={nameRef}
          autoFocus
          isRequired
          autoComplete="off"
          enterKeyHint="next"
          label="ФИО"
          value={name}
          {...fe.field("full_name", setName)}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            phoneRef.current?.focus();
          }}
        />
        <Input
          ref={phoneRef}
          autoComplete="off"
          enterKeyHint="done"
          inputMode="tel"
          label="Телефон"
          placeholder="+992 90 123 45 67"
          type="tel"
          value={phone}
          {...fe.field("phone", setPhone)}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            run(false);
          }}
        />
        <div>
          <p className="mb-1.5 text-sm text-default-600">Пол</p>
          <Segmented
            label="Пол"
            options={GENDERS}
            value={gender}
            onChange={(g) => {
              fe.clear("gender");
              setGender(g);
            }}
          />
          {fe.hint("gender").errorMessage && <p className="mt-1 text-xs text-danger">{fe.hint("gender").errorMessage}</p>}
        </div>
        {pickDonor && (
          <SelectField
            allLabel={funding && priced(funding) ? "Платит сам" : undefined}
            isRequired={funding === "донор"}
            label={funding === "донор" ? "Донор" : "Кто платит"}
            options={payers}
            value={donorId}
            {...fe.hint(fe.hint("not_paying").errorMessage ? "not_paying" : "donor_id")}
            onChange={(v) => {
              fe.clear("donor_id");
              fe.clear("not_paying");
              setDonorId(v);
            }}
          />
        )}
        {running && (
          <DateField
            isRequired
            description="Уроки до этой даты нельзя отметить"
            label="Дата зачисления"
            max={today}
            min={start}
            value={enrolledOn}
            {...fe.field("enrolled_on", setEnrolledOn)}
          />
        )}
        <OverCapacityNotice fill={fill} />
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
    </AppModal>
  );
}
