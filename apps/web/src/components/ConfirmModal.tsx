"use client";

import type { ReactNode } from "react";
import { Button } from "@heroui/button";

import { AppModal } from "./AppModal";

export function ConfirmModal({
  isOpen,
  title,
  children,
  confirmLabel,
  danger = false,
  isLoading = false,
  onConfirm,
  onClose,
}: {
  isOpen: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  isLoading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <Button color={danger ? "danger" : "primary"} isLoading={isLoading} onPress={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
      isOpen={isOpen}
      size="md"
      title={title}
      onClose={onClose}
    >
      <div className="text-default-600">{children}</div>
    </AppModal>
  );
}
