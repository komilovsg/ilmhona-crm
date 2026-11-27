"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input, Textarea } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { LoadingButton } from "@/components/LoadingButton";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";

export type Donor = {
  id: string;
  version: number;
  name: string;
  note: string | null;
  archived: boolean;
  cohorts: number;
  students: number;
};

export function DonorFormModal({ donor, onClose, onSaved }: { donor: Donor | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(donor?.name ?? "");
  const [note, setNote] = useState(donor?.note ?? "");
  const valid = !!name.trim();
  const values = { name: name.trim(), note: note.trim() || null };
  const done = () => {
    onSaved();
    notify(donor ? "Донор сохранён" : "Донор добавлен");
    onClose();
  };
  const create = useMutation({
    mutationFn: () => api("/api/v1/donors", { method: "POST", body: values }),
    onSuccess: done,
  });
  const edit = useVersionedSave({
    record: donor,
    values,
    toValues: (d) => ({ name: d.name, note: d.note }),
    apply: (v) => {
      setName(v.name);
      setNote(v.note ?? "");
    },
    request: (changed, version) => api(`/api/v1/donors/${donor?.id}`, { method: "PATCH", body: changed, version }),
    labels: { name: "Название", note: "Заметка" },
    onSaved: done,
  });
  const fe = useFieldErrors(donor ? edit.failure : create.error, ["name", "note"]);
  const submit = useSubmit(() => (donor ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
            {donor ? "Сохранить" : "Добавить"}
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title={donor ? "Донор" : "Новый донор"}
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        <Input isRequired label="Название" maxLength={200} value={name} {...fe.field("name", setName)} />
        <Textarea label="Заметка" maxLength={1000} minRows={2} value={note} {...fe.field("note", setNote)} />
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
