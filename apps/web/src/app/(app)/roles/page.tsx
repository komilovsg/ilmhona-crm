"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Input } from "@heroui/input";
import { Radio, RadioGroup } from "@heroui/radio";
import { Spinner } from "@heroui/spinner";

import { AppModal } from "@/components/AppModal";
import { ConfirmModal } from "@/components/ConfirmModal";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { useMe, useRoles, useSections } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { can, fromMatrix, toMatrix, type MatrixChoice } from "@/lib/permissions";
import { submitOnce } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { RoleRow, SectionInfo } from "@/lib/types";

const CHOICES: { value: MatrixChoice; label: string }[] = [
  { value: "none", label: "Нет" },
  { value: "view", label: "Просмотр" },
  { value: "change", label: "Изменение" },
];

function RoleEditor({ role, sections, canChange, onDeleted }: {
  role: RoleRow;
  sections: SectionInfo[];
  canChange: boolean;
  onDeleted: () => void;
}) {
  const queryClient = useQueryClient();
  const keys = sections.map((s) => s.key);
  const [name, setName] = useState(role.name);
  const [matrix, setMatrix] = useState(() => toMatrix(role.permissions, keys));
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const readOnly = role.locked || !canChange;
  const sorted = (p: Record<string, string>) => JSON.stringify(Object.entries(p).sort());
  const dirty = name.trim() !== role.name || sorted(fromMatrix(matrix)) !== sorted(role.permissions);

  const save = useMutation({
    mutationFn: () =>
      api<RoleRow>(`/api/v1/roles/${role.id}`, { method: "PUT", body: { name, permissions: fromMatrix(matrix) } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      setError(null);
      notify("Роль сохранена");
    },
    onError: (e) => setError(messageOf(e)),
  });
  const remove = useMutation({
    mutationFn: () => api(`/api/v1/roles/${role.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
      notify("Роль удалена");
      onDeleted();
    },
    onError: (e) => {
      setConfirmDelete(false);
      notifyError(e);
    },
  });

  return (
    <section className="rounded-2xl bg-content1 p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{role.name}</h2>
        {role.locked && (
          <Chip size="sm" variant="flat">
            Все права, не редактируется
          </Chip>
        )}
        {role.is_system && !role.locked && (
          <Chip size="sm" variant="flat">
            Системная
          </Chip>
        )}
        <span className="text-sm text-default-500">Пользователей: {role.users_count}</span>
      </div>

      <Input isDisabled={readOnly} label="Название" value={name} onValueChange={setName} />

      <p className="mb-1 mt-5 text-xs text-default-500">«Изменение» включает удаление.</p>
      <ul className="divide-y divide-divider">
        {sections.map((s) => (
          <li key={s.key} className="flex flex-col gap-2 py-3 md:flex-row md:items-center md:justify-between">
            <span className="text-sm font-medium">{s.label}</span>
            <RadioGroup
              aria-label={s.label}
              isDisabled={readOnly}
              orientation="horizontal"
              size="sm"
              value={matrix[s.key]}
              onValueChange={(v) => setMatrix({ ...matrix, [s.key]: v as MatrixChoice })}
            >
              {CHOICES.map((c) => (
                <Radio key={c.value} value={c.value}>
                  {c.label}
                </Radio>
              ))}
            </RadioGroup>
          </li>
        ))}
      </ul>

      {error && (
        <p className="mt-3 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      {!readOnly && (
        <div className="mt-4 flex flex-wrap justify-between gap-2">
          <Button
            color="primary"
            isDisabled={!dirty || !name.trim()}
            isLoading={save.isPending}
            onPress={() => submitOnce(save.isPending, () => save.mutate())()}
          >
            Сохранить
          </Button>
          {!role.is_system && (
            <Button
              color="danger"
              startContent={<Icon name="trash" size={16} />}
              variant="light"
              onPress={() => setConfirmDelete(true)}
            >
              Удалить роль
            </Button>
          )}
        </div>
      )}
      <ConfirmModal
        confirmLabel="Удалить"
        danger
        isLoading={remove.isPending}
        isOpen={confirmDelete}
        title="Удалить роль"
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => submitOnce(remove.isPending, () => remove.mutate())()}
      >
        Роль «{role.name}» будет удалена. Если она назначена пользователям, сначала смените им роль.
      </ConfirmModal>
    </section>
  );
}

function NewRoleModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api<RoleRow>("/api/v1/roles", { method: "POST", body: { name, permissions: {} } }),
    onSuccess: (role) => {
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
      onCreated(role.id);
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color="primary" isDisabled={!name.trim()} isLoading={create.isPending} onPress={() => submitOnce(create.isPending, () => create.mutate())()}>
            Создать
          </Button>
        </>
      }
      isOpen
      size="md"
      title="Новая роль"
      onClose={onClose}
    >
      <form
        onSubmit={submitOnce(create.isPending || !name.trim(), () => create.mutate())}
      >
        <Input autoFocus isRequired label="Название" value={name} onValueChange={setName} />
        <p className="mt-2 text-xs text-default-500">Права отметите после создания.</p>
        {error && (
          <p className="mt-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </AppModal>
  );
}

export default function RolesPage() {
  const { data: me } = useMe();
  const { data: roles, isPending } = useRoles();
  const { data: sections } = useSections();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // Roles are global: only a user not bound to a branch may write them (the API enforces it too).
  const canChange = can(me?.permissions, "users", "change") && !me?.branch;
  const selected = roles?.find((r) => r.id === selectedId) ?? roles?.[0];

  return (
    <>
      <PageHeader
        actions={
          canChange && (
            <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setCreating(true)}>
              Роль
            </Button>
          )
        }
        title="Роли и права"
      />
      {isPending || !sections ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <div className="grid items-start gap-5 md:grid-cols-[18rem_1fr]">
          <ul className="space-y-2" aria-label="Роли">
            {roles?.map((r) => (
              <li key={r.id}>
                <button
                  aria-current={r.id === selected?.id}
                  className={`flex w-full items-center justify-between rounded-xl px-4 py-3 text-left transition-colors ${
                    r.id === selected?.id ? "bg-primary/10 text-brand-text" : "bg-content1 hover:bg-default-100"
                  }`}
                  type="button"
                  onClick={() => setSelectedId(r.id)}
                >
                  <span className="font-medium">{r.name}</span>
                  <span className="text-xs text-default-500">{r.users_count}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected && (
            <RoleEditor
              key={selected.id + JSON.stringify(Object.entries(selected.permissions).sort()) + selected.name}
              canChange={canChange}
              role={selected}
              sections={sections}
              onDeleted={() => setSelectedId(null)}
            />
          )}
        </div>
      )}
      {creating && <NewRoleModal onClose={() => setCreating(false)} onCreated={setSelectedId} />}
    </>
  );
}
