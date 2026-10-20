"use client";

import { Button } from "@heroui/button";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";

import { Icon } from "./Icon";

export type MenuAction = { key: string; label: string; icon: string; danger?: boolean };

/** The «…» menu of a row or card. */
export function RowMenu({
  actions,
  label,
  onAction,
}: {
  actions: MenuAction[];
  label: string;
  onAction: (key: string) => void;
}) {
  return (
    <Dropdown placement="bottom-end">
      <DropdownTrigger>
        <Button isIconOnly aria-label={label} size="sm" variant="light">
          <Icon name="more" size={18} />
        </Button>
      </DropdownTrigger>
      <DropdownMenu aria-label={label} onAction={(key) => onAction(String(key))}>
        {actions.map((a) => (
          <DropdownItem
            key={a.key}
            className={a.danger ? "text-danger" : undefined}
            color={a.danger ? "danger" : "default"}
            startContent={<Icon name={a.icon} size={16} />}
          >
            {a.label}
          </DropdownItem>
        ))}
      </DropdownMenu>
    </Dropdown>
  );
}
