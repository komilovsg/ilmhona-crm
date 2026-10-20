"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { SelectField } from "@/components/SelectField";
import { useBranches, useMe, useRoles } from "@/hooks/queries";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { TempPassword, UserRow } from "@/lib/types";
import { LoadingButton } from "@/components/LoadingButton";

/** Create (no `user`) or edit a user. Creating returns the temporary password through `onCreated`. */
export function UserFormModal({
  user,
  onClose,
  onCreated,
}: {
  user: UserRow | null;
  onClose: () => void;
  onCreated: (result: TempPassword) => void;
}) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: roles = [] } = useRoles();
  const [login, setLogin] = useState(user?.login ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  // A branch-bound manager works inside their own branch only.
  const [branchId, setBranchId] = useState<string | null>(user ? user.branch_id : (me?.branch?.id ?? null));
  const [roleId, setRoleId] = useState<string | null>(user?.role_id ?? null);
  const [error, setError] = useState<string | null>(null);
  const bound = !!me?.branch;

  const values = {
    full_name: fullName.trim(),
    phone: phone.trim() || null,
    email: email.trim() || null,
    branch_id: branchId,
    role_id: roleId,
  };
  const refreshLists = () => {
    void queryClient.invalidateQueries({ queryKey: ["users"] });
    void queryClient.invalidateQueries({ queryKey: ["roles"] });
  };
  const create = useMutation({
    mutationFn: () => api<TempPassword>("/api/v1/users", { method: "POST", body: { ...values, login } }),
    onSuccess: (result) => {
      refreshLists();
      onCreated(result);
      onClose();
    },
    onError: (e) => setError(messageOf(e)),
  });
  const edit = useVersionedSave({
    record: user,
    values,
    toValues: (u) => ({
      full_name: u.full_name,
      phone: u.phone,
      email: u.email,
      branch_id: u.branch_id,
      role_id: u.role_id as string | null,
    }),
    apply: (v) => {
      setFullName(v.full_name);
      setPhone(v.phone ?? "");
      setEmail(v.email ?? "");
      setBranchId(v.branch_id);
      setRoleId(v.role_id);
    },
    request: (changed, version) => api<UserRow>(`/api/v1/users/${user?.id}`, { method: "PATCH", body: changed, version }),
    labels: { full_name: "ФИО", phone: "Телефон", email: "Email", branch_id: "Филиал", role_id: "Роль" },
    show: {
      branch_id: (id: string | null) => branches.find((b) => b.id === id)?.name ?? "Все филиалы",
      role_id: (id: string | null) => roles.find((r) => r.id === id)?.name ?? "—",
    },
    onSaved: () => {
      refreshLists();
      notify("Пользователь сохранён");
      onClose();
    },
  });

  const valid = fullName.trim() && roleId && (user || login.trim().length >= 3);
  const submit = useSubmit(() => (user ? edit.save(values) : create.mutateAsync()), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={create.isPending || edit.pending} onPress={() => submit()}>
            {user ? "Сохранить" : "Создать"}
          </LoadingButton>
        </>
      }
      isOpen
      title={user ? "Пользователь" : "Новый пользователь"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        id="user-form"
        onSubmit={submit}
      >
        <Input
          autoComplete="off"
          description={user ? undefined : "От 3 символов: буквы, цифры, . _ @ -"}
          isDisabled={!!user}
          isRequired
          label="Логин"
          value={login}
          onValueChange={setLogin}
        />
        <Input isRequired label="ФИО" value={fullName} onValueChange={setFullName} />
        <Input label="Телефон" type="tel" value={phone} onValueChange={setPhone} />
        <Input label="Email" type="email" value={email} onValueChange={setEmail} />
        <SelectField
          allLabel="Все филиалы"
          isDisabled={bound}
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branchId}
          onChange={setBranchId}
        />
        <SelectField
          isRequired
          label="Роль"
          options={roles
            .filter((r) => r.assignable || r.id === user?.role_id)
            .map((r) => ({ key: r.id, label: r.name }))}
          value={roleId}
          onChange={setRoleId}
        />
        {!user && (
          <p className="text-xs text-default-500">
            После создания вы увидите временный пароль на 7 дней. Сотрудник сменит его при первом входе.
          </p>
        )}
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
