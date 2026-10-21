"use client";

import { useRef, useState } from "react";

/**
 * Open state of a HeroUI Dropdown that runs the chosen action only after the menu has closed. An action that opens
 * a (lazy-loaded) modal in the same tick left the popover's portal open behind it, over the sheet.
 * Spread `dropdown` on <Dropdown> and pass `onAction` to <DropdownMenu>.
 */
export function useMenu(run: (key: string) => void) {
  const [isOpen, setOpen] = useState(false);
  const picked = useRef<string | null>(null);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next && picked.current !== null) {
      const key = picked.current;

      picked.current = null;
      window.setTimeout(() => run(key), 0);
    }
  };

  return {
    dropdown: { isOpen, onOpenChange },
    onAction: (key: string | number) => {
      picked.current = String(key);
      onOpenChange(false);
    },
  };
}
