"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "./AppModal";
import { LoadingButton } from "./LoadingButton";
import { Segmented } from "./Segmented";

import { useRefreshEducation } from "@/hooks/education";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { api } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { EnrollmentRow } from "@/lib/types";

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
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [gender, setGender] = useState<Gender>("none");
  const nameRef = useRef<HTMLInputElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  const again = useRef(false);

  const save = useMutation({
    mutationFn: () =>
      api<EnrollmentRow>(`/api/v1/cohorts/${cohortId}/enrollments`, {
        method: "POST",
        body: {
          new_student: { full_name: name, phone: phone.trim() || null, gender: gender === "none" ? null : gender },
        },
      }),
    onSuccess: (row) => {
      void refresh();
      onSaved?.(row);
      notify("Студент добавлен");
      if (!again.current) return onClose();
      setName("");
      setPhone("");
      setGender("none");
      save.reset();
      nameRef.current?.focus();
    },
  });
  const fe = useFieldErrors(save.error, ["full_name", "phone", "gender"]);
  const valid = !!name.trim();
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
            Сохранить и добавить ещё
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={save.isPending} onPress={() => run(false)}>
            Сохранить
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
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
    </AppModal>
  );
}
