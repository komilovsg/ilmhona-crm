"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { SelectField } from "@/components/SelectField";
import { useRefreshEducation } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { useVersionedSave } from "@/hooks/useVersionedSave";
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

  const values = { full_name: name.trim(), phone: phone.trim() || null, gender };
  const done = () => {
    void refresh();
    notify(student ? "Студент сохранён" : "Студент добавлен");
    onClose();
  };
  const create = useMutation({
    mutationFn: () => api("/api/v1/students", { method: "POST", body: { ...values, branch_id: branchId } }),
    onSuccess: done,
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: student,
    values,
    toValues: (s) => ({ full_name: s.full_name, phone: s.phone, gender: s.gender }),
    apply: (v) => {
      setName(v.full_name);
      setPhone(v.phone ?? "");
      setGender(v.gender);
    },
    request: (changed, version) =>
      api(`/api/v1/students/${student?.id}`, { method: "PATCH", body: changed, version }),
    labels: { full_name: "ФИО", phone: "Телефон", gender: "Пол" },
    show: { gender: (g: string | null) => (g === "male" ? "Мужской" : g === "female" ? "Женский" : "—") },
    onSaved: done,
  });
  const pending = create.isPending || edit.pending;
  const submit = useSubmit(() => (student ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!valid} isLoading={pending} onPress={() => submit()}>
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
