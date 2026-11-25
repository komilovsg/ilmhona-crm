"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Textarea } from "@heroui/input";

import { AppModal } from "@/components/AppModal";
import { LoadingButton } from "@/components/LoadingButton";

/** A dialog with one text the API requires: the reissue / issue comment or the revoke reason. */
export function CertCommentModal({
  title,
  intro,
  label,
  confirmLabel,
  danger = false,
  required = true,
  isLoading,
  onSubmit,
  onClose,
}: {
  title: string;
  intro: string;
  label: string;
  confirmLabel: string;
  danger?: boolean;
  required?: boolean;
  isLoading: boolean;
  onSubmit: (text: string) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const ready = !required || text.trim().length > 0;

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color={danger ? "danger" : "primary"} isDisabled={!ready} isLoading={isLoading} onPress={() => onSubmit(text.trim())}>
            {confirmLabel}
          </LoadingButton>
        </>
      }
      isOpen
      size="md"
      title={title}
      onClose={onClose}
    >
      <div className="space-y-3">
        <p className="text-sm text-default-600">{intro}</p>
        <Textarea isRequired={required} label={label} maxLength={500} minRows={2} value={text} onValueChange={setText} />
      </div>
    </AppModal>
  );
}
