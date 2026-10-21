"use client";

import type { ReactNode } from "react";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";

import { useIsPhone, useReducedMotion } from "@/lib/client-store";
import { modalMotion, modalMotionReduced } from "@/lib/motion";

/**
 * The one modal of the app. Closes on Esc and on a click outside (bug #16: the old system's
 * dialogs ignored Esc) — never pass `isKeyboardDismissDisabled`. Full screen on a phone.
 */
export function AppModal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = "lg",
}: {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "2xl";
}) {
  const phone = useIsPhone();
  const reduced = useReducedMotion();

  return (
    <Modal
      isOpen={isOpen}
      isDismissable
      isKeyboardDismissDisabled={false}
      motionProps={reduced ? modalMotionReduced : modalMotion}
      scrollBehavior="inside"
      size={phone ? "full" : size}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <ModalContent>
        <ModalHeader className="text-lg">{title}</ModalHeader>
        <ModalBody>{children}</ModalBody>
        {footer && <ModalFooter className="flex-col-reverse gap-2 sm:flex-row">{footer}</ModalFooter>}
      </ModalContent>
    </Modal>
  );
}
