"use client";

import { useState } from "react";
import { Button } from "@heroui/button";

import { AppModal } from "./AppModal";
import { Icon } from "./Icon";

import { formatDateTime } from "@/lib/format";

/** The temporary password, shown once: the API stores only its hash. */
export function TempPasswordModal({
  login,
  password,
  expiresAt,
  onClose,
}: {
  login: string;
  password: string;
  expiresAt: string | null | undefined;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      // clipboard is blocked: the password stays selectable on screen
    }
  }

  return (
    <AppModal
      footer={
        <Button color="primary" onPress={onClose}>
          Готово
        </Button>
      }
      isOpen
      size="md"
      title="Временный пароль"
      onClose={onClose}
    >
      <p className="text-sm text-default-600">
        Передайте пароль сотруднику. Он показывается <b>один раз</b> и действует до{" "}
        {formatDateTime(expiresAt)}; при первом входе его нужно сменить.
      </p>
      <dl className="space-y-3 rounded-xl bg-default-100 p-4">
        <div>
          <dt className="text-xs text-default-500">Логин</dt>
          <dd className="font-medium">{login}</dd>
        </div>
        <div>
          <dt className="text-xs text-default-500">Пароль</dt>
          <dd className="flex items-center justify-between gap-3">
            <code className="select-all text-xl font-semibold tracking-wider">{password}</code>
            <Button
              size="sm"
              startContent={<Icon name={copied ? "check" : "copy"} size={16} />}
              variant="flat"
              onPress={() => void copy()}
            >
              {copied ? "Скопировано" : "Копировать"}
            </Button>
          </dd>
        </div>
      </dl>
    </AppModal>
  );
}
