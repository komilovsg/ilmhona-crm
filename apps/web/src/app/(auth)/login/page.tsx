"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Checkbox } from "@heroui/checkbox";
import { Input } from "@heroui/input";

import { LoadingButton } from "@/components/LoadingButton";
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
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loginRef = useRef<HTMLInputElement>(null);

  // Focus after hydration instead of the autoFocus prop: HeroUI renders a different caret-color
  // on the server and the client for an autoFocus input, which logs a hydration mismatch.
  useEffect(() => loginRef.current?.focus(), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("/api/v1/auth/login", { method: "POST", body: { login, password, remember } });

      queryClient.setQueryData(ME_KEY, me);
      router.replace(me.must_change_password ? "/change-password" : homePath(me.permissions));
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Вход</h1>
      <p className="mb-6 mt-1 text-sm text-default-600">Логин и пароль выдаёт администратор.</p>
      <form className="space-y-4" onSubmit={submit}>
        <Input
          ref={loginRef}
          autoCapitalize="none"
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
        <div className="flex items-center justify-between gap-3">
          <Checkbox isSelected={remember} size="sm" onValueChange={setRemember}>
            Запомнить меня
          </Checkbox>
          <Link className="text-sm text-brand-text underline-offset-2 hover:underline" href="/forgot-password">
            Забыли пароль?
          </Link>
        </div>
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <LoadingButton fullWidth color="primary" isDisabled={!login || !password} isLoading={busy} size="lg" type="submit">
          Войти
        </LoadingButton>
      </form>
    </>
  );
}
