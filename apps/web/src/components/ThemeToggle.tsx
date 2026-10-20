"use client";

import { Button } from "@heroui/button";

import { Icon } from "./Icon";

import { useTheme } from "@/context/ThemeContext";
import type { ThemePreference } from "@/context/theme-init";

const OPTIONS: { value: ThemePreference; label: string; icon: string }[] = [
  { value: "light", label: "Светлая тема", icon: "sun" },
  { value: "dark", label: "Тёмная тема", icon: "moon" },
  { value: "system", label: "Как в системе", icon: "system" },
];

/** Light / dark / system, in the header. */
export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <div className="flex gap-0.5 rounded-full bg-default-100 p-0.5" role="group" aria-label="Тема">
      {OPTIONS.map((o) => (
        <Button
          key={o.value}
          isIconOnly
          aria-label={o.label}
          aria-pressed={preference === o.value}
          className={preference === o.value ? "bg-content1 text-foreground shadow-sm" : "text-default-500"}
          radius="full"
          size="sm"
          title={o.label}
          variant="light"
          onPress={() => setPreference(o.value)}
        >
          <Icon name={o.icon} size={16} />
        </Button>
      ))}
    </div>
  );
}
