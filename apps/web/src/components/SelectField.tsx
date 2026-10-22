"use client";

import { Select, SelectItem } from "@heroui/select";
import { useOverlayMotion } from "@/lib/motion";

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
  isInvalid,
  errorMessage,
  onChange,
}: {
  label: string;
  value: string | null;
  options: Option[];
  allLabel?: string;
  isDisabled?: boolean;
  isRequired?: boolean;
  className?: string;
  isInvalid?: boolean;
  errorMessage?: string;
  onChange: (value: string | null) => void;
}) {
  const items: Option[] = allLabel ? [{ key: ALL, label: allLabel }, ...options] : options;
  const selected = value ?? (allLabel ? ALL : null);
  const overlayMotion = useOverlayMotion();

  return (
    <Select
      popoverProps={{ motionProps: overlayMotion }}
      className={className}
      disallowEmptySelection
      errorMessage={errorMessage}
      isDisabled={isDisabled}
      isInvalid={isInvalid}
      isRequired={isRequired}
      items={items}
      label={label}
      selectedKeys={selected ? [selected] : []}
      onSelectionChange={(keys) => {
        const key = [...keys][0];

        onChange(key === undefined || key === ALL ? null : String(key));
      }}
    >
      {(item) => (
        // long labels (the payment month states) wrap instead of being cut on a phone
        <SelectItem key={item.key} classNames={{ title: "whitespace-normal break-words" }}>
          {item.label}
        </SelectItem>
      )}
    </Select>
  );
}
