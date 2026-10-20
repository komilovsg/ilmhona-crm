"use client";

import { Select, SelectItem } from "@heroui/select";

const ALL = "__all__";

export type Option = { key: string; label: string };

/**
 * Single select. With `allLabel` the first entry means "nothing chosen" and reports `null`
 * (filters: «Все филиалы»; forms: «Все филиалы» as a real value).
 */
export function SelectField({
  label,
  value,
  options,
  allLabel,
  isDisabled,
  isRequired,
  className,
  onChange,
}: {
  label: string;
  value: string | null;
  options: Option[];
  allLabel?: string;
  isDisabled?: boolean;
  isRequired?: boolean;
  className?: string;
  onChange: (value: string | null) => void;
}) {
  const items: Option[] = allLabel ? [{ key: ALL, label: allLabel }, ...options] : options;
  const selected = value ?? (allLabel ? ALL : null);

  return (
    <Select
      className={className}
      disallowEmptySelection
      isDisabled={isDisabled}
      isRequired={isRequired}
      items={items}
      label={label}
      selectedKeys={selected ? [selected] : []}
      onSelectionChange={(keys) => {
        const key = [...keys][0];

        onChange(key === undefined || key === ALL ? null : String(key));
      }}
    >
      {(item) => <SelectItem key={item.key}>{item.label}</SelectItem>}
    </Select>
  );
}
