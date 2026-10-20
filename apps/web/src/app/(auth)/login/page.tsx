"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";

import { Logo } from "@/components/Logo";
import { PasswordField } from "@/components/PasswordField";
import { ME_KEY } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { homePath } from "@/lib/permissions";
import type { Me } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("/api/v1/auth/login", { method: "POST", body: { login, password } });

      queryClient.setQueryData(ME_KEY, me);
      router.replace(me.must_change_password ? "/change-password" : homePath(me.permissions));
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl bg-content1 p-6 shadow-lg sm:p-8">
      <div className="mb-6 rounded-xl bg-sidebar px-5 py-4">
        <Logo />
      </div>
      <h1 className="mb-1 text-xl font-semibold">Вход</h1>
      <p className="mb-5 text-sm text-default-500">Логин и пароль выдаёт администратор.</p>
      <form className="space-y-4" onSubmit={submit}>
        <Input
          autoFocus
          autoComplete="username"
          label="Логин"
          value={login}
          onValueChange={setLogin}
        />
        <PasswordField
          autoComplete="current-password"
          label="Пароль"
          value={password}
          onValueChange={setPassword}
        />
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <Button fullWidth color="primary" isDisabled={!login || !password} isLoading={busy} type="submit">
          Войти
        </Button>
      </form>
    </div>
  );
}
