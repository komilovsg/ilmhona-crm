"use client";

import { Input, type InputProps } from "@heroui/input";

import { FILTER_H } from "@/lib/filter-controls";

/** A text input in a filter row (search): the shared filter height, everything else as `Input`. */
export function FilterInput({ classNames, ...props }: InputProps) {
  return <Input classNames={{ ...classNames, inputWrapper: `${FILTER_H} ${classNames?.inputWrapper ?? ""}` }} {...props} />;
}
