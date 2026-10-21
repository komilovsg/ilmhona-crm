"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { NewPasswordFields, usePasswordRules } from "@/components/NewPasswordFields";
import { PasswordField } from "@/components/PasswordField";
import { ME_KEY, useMe } from "@/hooks/queries";
import { api, messageOf } from "@/lib/api";
import { homePath } from "@/lib/permissions";
import type { Me } from "@/lib/types";
import { LoadingButton } from "@/components/LoadingButton";

/** Forced after the first sign-in with a temporary password: the only page the API allows then. */
export default function ChangePasswordPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: me } = useMe();
  const { rules, valid } = usePasswordRules(next, repeat, me?.login ?? "", current);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api<Me>("/api/v1/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });

      queryClient.setQueryData(ME_KEY, updated);
      router.replace(homePath(updated.permissions));
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  }

  async function logout() {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <div className="rounded-2xl bg-content1 p-6 shadow-lg sm:p-8">
      <h1 className="mb-1 text-xl font-semibold">Смените пароль</h1>
      <p className="mb-5 text-sm text-default-500">
        Вы вошли с временным паролем. Задайте свой, он должен пройти все проверки ниже.
      </p>
      <form className="space-y-4" onSubmit={submit}>
        <PasswordField
          autoComplete="current-password"
          label="Временный пароль"
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
          fullWidth
          color="primary"
          isDisabled={!current || !valid}
          isLoading={busy}
          type="submit"
        >
          Сохранить пароль
        </LoadingButton>
        <Button fullWidth variant="light" onPress={() => void logout()}>
          Выйти
        </Button>
      </form>
    </div>
  );
}
