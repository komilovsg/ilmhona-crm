"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Input } from "@heroui/input";

import { ConflictDialog } from "@/components/ConflictDialog";
import { PageHeader } from "@/components/PageHeader";
import { NewPasswordFields, usePasswordRules } from "@/components/NewPasswordFields";
import { PasswordField } from "@/components/PasswordField";
import { SessionsList } from "@/components/SessionsList";
import { ME_KEY, useMe } from "@/hooks/queries";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api, messageOf } from "@/lib/api";
import { useSubmit } from "@/lib/submit";
import { notify } from "@/lib/toast";
import type { Me } from "@/lib/types";
import { LoadingButton } from "@/components/LoadingButton";

function ProfileForm({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState(me.full_name);
  const [phone, setPhone] = useState(me.phone ?? "");
  const [email, setEmail] = useState(me.email ?? "");
  const [login, setLogin] = useState(me.login);
  // Only a superadmin edits a login (through the users endpoint); everyone else sees it fixed.
  const isSuper = me.role.code === "superadmin";
  const values = { login: login.trim(), full_name: fullName.trim(), phone: phone.trim() || null, email: email.trim() || null };
  const save = useVersionedSave({
    record: me,
    values,
    toValues: (m) => ({ login: m.login, full_name: m.full_name, phone: m.phone, email: m.email }),
    apply: (v) => {
      setLogin(v.login);
      setFullName(v.full_name);
      setPhone(v.phone ?? "");
      setEmail(v.email ?? "");
    },
    request: async (changed, version) => {
      if (!isSuper) return api<Me>("/api/v1/auth/me", { method: "PATCH", body: changed, version });
      await api(`/api/v1/users/${me.id}`, { method: "PATCH", body: changed, version });
      return api<Me>("/api/v1/auth/me");
    },
    labels: { login: "Логин", full_name: "ФИО", phone: "Телефон", email: "Email" },
    onSaved: (updated) => {
      if (updated) queryClient.setQueryData(ME_KEY, updated);
      notify("Профиль сохранён");
    },
  });

  const submit = useSubmit(() => save.save(values));

  return (
    <form
      className="space-y-4 rounded-2xl bg-content1 p-5"
      onSubmit={submit}
    >
      <h2 className="text-lg font-semibold">Данные</h2>
      <Input
        description={isSuper ? "3–40 символов: латинские буквы, цифры, . _ -" : undefined}
        isReadOnly={!isSuper}
        label={isSuper ? "Логин" : "Логин (нельзя изменить)"}
        value={login}
        onValueChange={setLogin}
      />
      <Input isRequired label="ФИО" value={fullName} onValueChange={setFullName} />
      <Input label="Телефон" type="tel" value={phone} onValueChange={setPhone} />
      <Input label="Email" type="email" value={email} onValueChange={setEmail} />
      <p className="text-xs text-default-500">
        Роль: {me.role.name} · {me.branch ? me.branch.name : "все филиалы"}
      </p>
      {save.error && (
        <p className="text-sm text-danger" role="alert">
          {save.error}
        </p>
      )}
      <LoadingButton color="primary" isDisabled={!fullName.trim() || login.trim().length < 3} isLoading={save.pending} type="submit">
        Сохранить
      </LoadingButton>
      <ConflictDialog save={save} />
    </form>
  );
}

function PasswordForm({ login }: { login: string }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { rules, valid } = usePasswordRules(next, repeat, login, current);
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
      <NewPasswordFields next={next} repeat={repeat} rules={rules} onNext={setNext} onRepeat={setRepeat} />
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <LoadingButton
        color="primary"
        isDisabled={!current || !valid}
        isLoading={change.isPending}
        type="submit"
      >
        Сменить пароль
      </LoadingButton>
    </form>
  );
}

function SessionsCard() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return (
    <section className="rounded-2xl bg-content1 p-5 md:col-span-2">
      <h2 className="text-lg font-semibold">Мои устройства и сессии</h2>
      <p className="mb-2 text-sm text-default-600">Где открыт ваш аккаунт. Незнакомое устройство можно отключить.</p>
      <SessionsList
        base="/api/v1/auth"
        own
        onSignedOut={() => {
          queryClient.clear();
          router.replace("/login");
        }}
      />
    </section>
  );
}

export default function ProfilePage() {
  const { data: me } = useMe();

  return (
    <>
      <PageHeader title="Профиль" />
      {me && (
        <div className="grid gap-5 md:grid-cols-2">
          <ProfileForm key={me.id} me={me} />
          <PasswordForm login={me.login} />
          <SessionsCard />
        </div>
      )}
    </>
  );
}
