"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";

import { Icon } from "./Icon";
import { SheetHandle } from "./SheetHandle";

import { useIsPhone } from "@/lib/client-store";
import { useOverlayMotion } from "@/lib/motion";

/** The filters a list does not need every minute: a «Фильтры · N» button and a panel (from the
 * right on a desktop, a bottom sheet on a phone). The one or two quick ones stay in the row. */
export function FilterDrawer({
  count,
  onReset,
  children,
}: {
  /** how many of the hidden filters are set */
  count: number;
  onReset: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const phone = useIsPhone();
  const overlayMotion = useOverlayMotion();

  return (
    <>
      <Button
        className="h-12 shrink-0"
        color="primary"
        startContent={<Icon name="filter" size={18} />}
        variant="flat"
        onPress={() => setOpen(true)}
      >
        Фильтры
        {count > 0 && (
          <span className="ml-1 inline-flex size-5 items-center justify-center rounded-full bg-primary text-xs tabular-nums text-primary-foreground">
            {count}
          </span>
        )}
      </Button>
      <Drawer isOpen={open} motionProps={overlayMotion} placement={phone ? "bottom" : "right"} size="sm" onOpenChange={setOpen}>
        <DrawerContent>
          {(close) => (
            <>
              {phone && <SheetHandle onBackdrop={close} onClose={close} />}
              <DrawerHeader>Фильтры</DrawerHeader>
              <DrawerBody className="gap-3">{children}</DrawerBody>
              <DrawerFooter>
                <Button isDisabled={count === 0} variant="light" onPress={onReset}>
                  Сбросить
                </Button>
                <Button color="primary" onPress={close}>
                  Показать
                </Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>
    </>
  );
}
