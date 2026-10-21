"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@heroui/button";
import { Modal, ModalBody, ModalContent, ModalFooter, ModalHeader } from "@heroui/modal";

import { useIsPhone, useReducedMotion } from "@/lib/client-store";
import { modalMotion, overlayFade, sheetMotion } from "@/lib/motion";
import { dismissAction, isEditField } from "@/lib/sheet";
import { SheetHandle } from "./SheetHandle";

/**
 * The one modal of the app. Centred on desktop; a bottom sheet under 768 px (grab handle, follows the finger,
 * swipe down to close, content scrolls inside, keyboard-aware). Closes on Esc, a click outside and a swipe
 * (bug #16: the old system's dialogs ignored Esc) — never pass `isKeyboardDismissDisabled`.
 *
 * Unsaved changes: once the user has edited a field, Esc / backdrop / swipe ask «Закрыть без сохранения?»
 * first. The buttons of the dialog itself (Cancel, Save) call `onClose` directly and are never guarded.
 * `guard={false}` turns the question off (the confirm itself, dialogs with no form).
 */
export function AppModal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = "lg",
  guard = true,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg" | "2xl";
  guard?: boolean;
}) {
  const phone = useIsPhone();
  const reduced = useReducedMotion();
  const [dirty, setDirty] = useState(false);
  const [asking, setAsking] = useState(false);
  const [wasOpen, setWasOpen] = useState(isOpen);

  if (wasOpen !== isOpen) {
    setWasOpen(isOpen);
    if (!isOpen) {
      setDirty(false);
      setAsking(false);
    }
  }

  /** Esc, backdrop and swipe come here. Returns false when the question is shown instead of closing. */
  function requestClose(): boolean {
    if (dismissAction({ dirty, guarded: guard }) === "confirm") {
      setAsking(true);

      return false;
    }
    onClose();

    return true;
  }

  const markDirty = (target: EventTarget, trusted: boolean) => {
    if (trusted && !dirty && isEditField(target as HTMLInputElement)) setDirty(true);
  };

  return (
    <>
      <Modal
        classNames={
          phone
            ? {
                base: "m-0 w-full max-w-none rounded-b-none rounded-t-2xl pb-[env(safe-area-inset-bottom)] max-h-[calc(var(--visual-viewport-height)-env(safe-area-inset-top)-12px)] will-change-transform",
                body: "overscroll-contain",
              }
            : undefined
        }
        isDismissable
        isKeyboardDismissDisabled={false}
        isOpen={isOpen}
        motionProps={reduced ? overlayFade : phone ? sheetMotion : modalMotion}
        placement={phone ? "bottom" : "auto"}
        scrollBehavior="inside"
        size={phone ? "md" : size}
        onOpenChange={(open) => {
          if (!open) requestClose();
        }}
      >
        <ModalContent>
          <SheetHandle canClose={requestClose} onClose={onClose} />
          <ModalHeader className="text-lg">{title}</ModalHeader>
          <ModalBody
            onChange={(e) => markDirty(e.target, e.nativeEvent.isTrusted)}
            onClick={(e) => {
              // react-aria selects / radios / switches change state without a native change event
              if (e.nativeEvent.isTrusted && !dirty && (e.target as HTMLElement).closest('[role="option"],[role="radio"],[role="switch"],[role="checkbox"]'))
                setDirty(true);
            }}
            onInput={(e) => markDirty(e.target, e.nativeEvent.isTrusted)}
          >
            {children}
          </ModalBody>
          {footer && <ModalFooter className="flex-col-reverse gap-2 sm:flex-row">{footer}</ModalFooter>}
        </ModalContent>
      </Modal>
      {asking && (
        <AppModal
          footer={
            <>
              <Button variant="light" onPress={() => setAsking(false)}>
                Продолжить
              </Button>
              <Button
                color="danger"
                onPress={() => {
                  setAsking(false);
                  onClose();
                }}
              >
                Закрыть без сохранения
              </Button>
            </>
          }
          guard={false}
          isOpen
          size="md"
          title="Закрыть без сохранения?"
          onClose={() => setAsking(false)}
        >
          <p className="text-default-600">Внесённые изменения будут потеряны.</p>
        </AppModal>
      )}
    </>
  );
}
