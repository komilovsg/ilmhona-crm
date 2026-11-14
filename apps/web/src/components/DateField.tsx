"use client";

import { Button } from "@heroui/button";
import { DatePicker } from "@heroui/date-picker";

import { Icon } from "@/components/Icon";

import { parseIso, toIso } from "@/lib/iso-date";
import { FILTER_H } from "@/lib/filter-controls";
import { useOverlayMotion } from "@/lib/motion";

/**
 * Date (or date + time) field shown as дд.мм.гггг. Takes and returns the ISO strings the pages keep
 * (`YYYY-MM-DD`, with `withTime` `YYYY-MM-DDTHH:mm`, "" for empty), so it replaces `<Input type="date">`
 * one to one, including `{...fe.field(name, set)}`.
 */
export function DateField({
  label,
  value,
  onValueChange,
  min,
  max,
  withTime,
  filter,
  isRequired,
  isInvalid,
  errorMessage,
  description,
  className,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  min?: string;
  max?: string;
  withTime?: boolean;
  /** sits in a filter row: the shared filter height */
  filter?: boolean;
  isRequired?: boolean;
  isInvalid?: boolean;
  errorMessage?: string;
  description?: string;
  className?: string;
}) {
  const overlayMotion = useOverlayMotion();

  return (
    <DatePicker
      className={className}
      classNames={filter ? { inputWrapper: FILTER_H } : undefined}
      description={description}
      endContent={
        value && !isRequired ? (
          <Button
            isIconOnly
            aria-label="Очистить дату"
            className="-mr-1 size-10 min-w-10 shrink-0"
            radius="full"
            size="sm"
            variant="light"
            onPress={() => onValueChange("")}
          >
            <Icon name="x" size={16} />
          </Button>
        ) : undefined
      }
      errorMessage={errorMessage}
      granularity={withTime ? "minute" : "day"}
      hourCycle={24}
      isInvalid={isInvalid}
      isRequired={isRequired}
      label={label}
      maxValue={parseIso(max, withTime) ?? undefined}
      minValue={parseIso(min, withTime) ?? undefined}
      popoverProps={{ motionProps: overlayMotion }}
      size={filter ? "sm" : "md"}
      value={parseIso(value, withTime)}
      onChange={(v) => onValueChange(toIso(v, withTime))}
    />
  );
}
