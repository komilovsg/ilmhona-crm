"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { SelectField } from "@/components/SelectField";
import { useBranches, useMe, useRoles } from "@/hooks/queries";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { TempPassword, UserRow } from "@/lib/types";
import { LoadingButton } from "@/components/LoadingButton";

const LOGIN_HINT = "3–40 символов: латинские буквы, цифры, . _ -";

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
  const bound = !!me?.branch;
  const isSuper = me?.role.code === "superadmin";

  const values = {
    login: login.trim(),
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
    mutationFn: () => api<TempPassword>("/api/v1/users", { method: "POST", body: values }),
    onSuccess: (result) => {
      refreshLists();
      onCreated(result);
      onClose();
    },
  });
  const edit = useVersionedSave({
    record: user,
    values,
    toValues: (u) => ({
      login: u.login,
      full_name: u.full_name,
      phone: u.phone,
      email: u.email,
      branch_id: u.branch_id,
      role_id: u.role_id as string | null,
    }),
    apply: (v) => {
      setLogin(v.login);
      setFullName(v.full_name);
      setPhone(v.phone ?? "");
      setEmail(v.email ?? "");
      setBranchId(v.branch_id);
      setRoleId(v.role_id);
    },
    request: (changed, version) => api<UserRow>(`/api/v1/users/${user?.id}`, { method: "PATCH", body: changed, version }),
    labels: { login: "Логин", full_name: "ФИО", phone: "Телефон", email: "Email", branch_id: "Филиал", role_id: "Роль" },
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

  const valid = fullName.trim() && roleId && login.trim().length >= 3;
  const fe = useFieldErrors(user ? edit.failure : create.error, ["login", "full_name", "phone", "email", "branch_id", "role_id"]);
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
          description={user && !isSuper ? "Логин может изменить только суперадмин" : LOGIN_HINT}
          isDisabled={!!user && !isSuper}
          isRequired
          label="Логин"
          value={login}
          {...fe.field("login", setLogin)}
        />
        <Input isRequired label="ФИО" value={fullName} {...fe.field("full_name", setFullName)} />
        <Input inputMode="tel" label="Телефон" placeholder="+992 90 123 45 67" type="tel" value={phone} {...fe.field("phone", setPhone)} />
        <Input label="Email" type="email" value={email} {...fe.field("email", setEmail)} />
        <SelectField
          allLabel="Все филиалы"
          isDisabled={bound}
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={branchId}
          onChange={(v) => {
            fe.clear("branch_id");
            setBranchId(v);
          }}
          {...fe.hint("branch_id")}
        />
        <SelectField
          isRequired
          label="Роль"
          options={roles
            .filter((r) => r.assignable || r.id === user?.role_id)
            .map((r) => ({ key: r.id, label: r.name }))}
          value={roleId}
          onChange={(v) => {
            fe.clear("role_id");
            setRoleId(v);
          }}
          {...fe.hint("role_id")}
        />
        {!user && (
          <p className="text-xs text-default-500">
            После создания вы увидите временный пароль на 7 дней. Сотрудник сменит его при первом входе.
          </p>
        )}
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
