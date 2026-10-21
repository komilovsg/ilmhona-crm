"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Input } from "@heroui/input";

import { LoadingButton } from "@/components/LoadingButton";
import { api, messageOf } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [login, setLogin] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ message: string }>("/api/v1/auth/forgot-password", { method: "POST", body: { login } });

      setAnswer(r.message);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Забыли пароль?</h1>
      {answer ? (
        <div className="mt-4 space-y-5">
          <p className="rounded-xl bg-content2 p-4 text-sm" role="status">
            {answer}. Новый временный пароль выдаст администратор.
          </p>
          <Link className="text-sm text-brand-text underline-offset-2 hover:underline" href="/login">
            Вернуться ко входу
          </Link>
        </div>
      ) : (
        <>
          <p className="mb-6 mt-1 text-sm text-default-600">
            Введите логин. Администратор получит запрос и выдаст временный пароль.
          </p>
          <form className="space-y-4" onSubmit={submit}>
            <Input autoCapitalize="none" autoComplete="username" label="Логин" value={login} onValueChange={setLogin} />
            {error && (
              <p className="text-sm text-danger" role="alert">
                {error}
              </p>
            )}
            <LoadingButton fullWidth color="primary" isDisabled={!login.trim()} isLoading={busy} size="lg" type="submit">
              Отправить запрос
            </LoadingButton>
            <Link className="block text-center text-sm text-brand-text underline-offset-2 hover:underline" href="/login">
              Вернуться ко входу
            </Link>
          </form>
        </>
      )}
    </>
  );
}
