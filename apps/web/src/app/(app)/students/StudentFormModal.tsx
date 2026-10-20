"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { SelectField } from "@/components/SelectField";
import { useRefreshEducation } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { StudentRow } from "@/lib/types";

export function StudentFormModal({ student, onClose }: { student: StudentRow | null; onClose: () => void }) {
  const refresh = useRefreshEducation();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const [name, setName] = useState(student?.full_name ?? "");
  const [phone, setPhone] = useState(student?.phone ?? "");
  const [gender, setGender] = useState<string | null>(student?.gender ?? null);
  const [branchId, setBranchId] = useState<string | null>(student?.branch_id ?? me?.branch?.id ?? null);
  const [error, setError] = useState<string | null>(null);
  const valid = name.trim() && (student || branchId);

  const save = useMutation({
    mutationFn: () => {
      const body = { full_name: name, phone: phone.trim() || null, gender };

      return student
        ? api(`/api/v1/students/${student.id}`, { method: "PATCH", body })
        : api("/api/v1/students", { method: "POST", body: { ...body, branch_id: branchId } });
    },
    onSuccess: () => {
      void refresh();
      notify(student ? "Студент сохранён" : "Студент добавлен");
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });
  const submit = useSubmit(() => save.mutateAsync(), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!valid} isLoading={save.isPending} onPress={() => submit()}>
            {student ? "Сохранить" : "Добавить"}
          </Button>
        </>
      }
      isOpen
      size="md"
      title={student ? "Студент" : "Новый студент"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={submit}
      >
        <Input isRequired label="ФИО" value={name} onValueChange={setName} />
        <Input label="Телефон" type="tel" value={phone} onValueChange={setPhone} />
        <SelectField
          allLabel="Не указан"
          label="Пол"
          options={[
            { key: "male", label: "Мужской" },
            { key: "female", label: "Женский" },
          ]}
          value={gender}
          onChange={setGender}
        />
        <SelectField
          isDisabled={!!student || !!me?.branch}
          isRequired
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branchId}
          onChange={setBranchId}
        />
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </AppModal>
  );
}
