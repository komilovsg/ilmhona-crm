"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";

import { ConfirmModal } from "./ConfirmModal";

import { useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { can } from "@/lib/permissions";
import { notifyError } from "@/lib/toast";
import type { TempPassword } from "@/lib/types";

const TempPasswordModal = dynamic(() => import("./TempPasswordModal").then((m) => m.TempPasswordModal));

/**
 * «Активировать» for an account without access: the same flow as in the users list (a new
 * temporary password for 7 days, shown once). Renders nothing for people who may not activate
 * (`users` change); the API checks the right and the branch again.
 */
export function ActivateUserButton({
  userId,
  name,
  active = false,
  className,
}: {
  userId: string;
  name: string;
  /** the account already has access: no button, but a password just issued stays on screen */
  active?: boolean;
  className?: string;
}) {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [temp, setTemp] = useState<{ login: string; password: string; expiresAt: string | null | undefined } | null>(null);
  const run = useMutation({
    mutationFn: () => api<TempPassword>(`/api/v1/users/${userId}/activate`, { method: "POST" }),
    onSuccess: (r) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      void queryClient.invalidateQueries({ queryKey: ["instructor-cards"] });
      setConfirm(false);
      setTemp({ login: r.user.login, password: r.temp_password, expiresAt: r.expires_at });
    },
    onError: (e) => {
      setConfirm(false);
      notifyError(e);
    },
  });

  if (!can(me?.permissions, "users", "change")) return null;

  return (
    <>
      {!active && (
        <div className={className}>
          <Button aria-label={`Активировать: ${name}`} size="sm" variant="flat" onPress={() => setConfirm(true)}>
            Активировать
          </Button>
        </div>
      )}
      <ConfirmModal
        confirmLabel="Выдать пароль"
        isLoading={run.isPending}
        isOpen={confirm}
        title="Активировать"
        onClose={() => setConfirm(false)}
        onConfirm={() => run.mutate()}
      >
        {`Для ${name} будет создан временный пароль на 7 дней, открытые сеансы закроются.`}
      </ConfirmModal>
      {temp && <TempPasswordModal {...temp} onClose={() => setTemp(null)} />}
    </>
  );
}
