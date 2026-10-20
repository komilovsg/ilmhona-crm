"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { PageHeader } from "@/components/PageHeader";
import { PasswordField } from "@/components/PasswordField";
import { ME_KEY, useMe } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";
import type { Me } from "@/lib/types";

function ProfileForm({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState(me.full_name);
  const [phone, setPhone] = useState(me.phone ?? "");
  const [email, setEmail] = useState(me.email ?? "");
  const save = useMutation({
    mutationFn: () =>
      api<Me>("/api/v1/auth/me", {
        method: "PATCH",
        body: { full_name: fullName, phone: phone || null, email: email || null },
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(ME_KEY, updated);
      notify("Профиль сохранён");
    },
    onError: notifyError,
  });

  const submit = useSubmit(() => save.mutateAsync());

  return (
    <form
      className="space-y-4 rounded-2xl bg-content1 p-5"
      onSubmit={submit}
    >
      <h2 className="text-lg font-semibold">Данные</h2>
      <Input isReadOnly label="Логин" value={me.login} />
      <Input isRequired label="ФИО" value={fullName} onValueChange={setFullName} />
      <Input label="Телефон" type="tel" value={phone} onValueChange={setPhone} />
      <Input label="Email" type="email" value={email} onValueChange={setEmail} />
      <p className="text-xs text-default-500">
        Роль: {me.role.name} · {me.branch ? me.branch.name : "все филиалы"}
      </p>
      <Button color="primary" isDisabled={!fullName.trim()} isLoading={save.isPending} type="submit">
        Сохранить
      </Button>
    </form>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: () =>
      api<Me>("/api/v1/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setRepeat("");
      setError(null);
      notify("Пароль изменён");
    },
    onError: (e) => setError(messageOf(e)),
  });

  const submit = useSubmit(() => change.mutateAsync());

  return (
    <form
      className="space-y-4 rounded-2xl bg-content1 p-5"
      onSubmit={submit}
    >
      <h2 className="text-lg font-semibold">Смена пароля</h2>
      <PasswordField
        autoComplete="current-password"
        label="Текущий пароль"
        value={current}
        onValueChange={setCurrent}
      />
      <PasswordField
        autoComplete="new-password"
        description="8–72 символа, буква, цифра и спецсимвол"
        label="Новый пароль"
        value={next}
        onValueChange={setNext}
      />
      <PasswordField
        autoComplete="new-password"
        errorMessage="Пароли не совпадают"
        isInvalid={repeat !== "" && repeat !== next}
        label="Повторите новый пароль"
        value={repeat}
        onValueChange={setRepeat}
      />
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Button
        color="primary"
        isDisabled={!current || !next || next !== repeat}
        isLoading={change.isPending}
        type="submit"
      >
        Сменить пароль
      </Button>
    </form>
  );
}

export default function ProfilePage() {
  const { data: me } = useMe();

  return (
    <>
      <PageHeader title="Профиль" />
      {me && (
        <div className="grid gap-5 md:grid-cols-2">
          <ProfileForm key={me.id + me.full_name} me={me} />
          <PasswordForm />
        </div>
      )}
    </>
  );
}
