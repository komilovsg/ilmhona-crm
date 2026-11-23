"use client";

import { useEffect, useState } from "react";
import { Input, type InputProps } from "@heroui/input";

import { FILTER_H } from "@/lib/filter-controls";

const DELAY = 300; // ms without a keystroke before the list is asked again

/** A text input in a filter row (search): the shared filter height, everything else as `Input`.
 * Typing is shown at once and reported after a short pause, so a slow connection gets one
 * request per word, not one per letter. Clearing is reported at once. */
export function FilterInput({ classNames, value, onValueChange, onClear, ...props }: InputProps) {
  const [text, setText] = useState(value ?? "");
  const [reported, setReported] = useState(value ?? "");

  // the filter was changed from outside (reset, Back): show it
  if (value !== undefined && value !== reported) {
    setReported(value);
    setText(value);
  }

  useEffect(() => {
    if (text === reported) return;
    const timer = setTimeout(() => {
      setReported(text);
      onValueChange?.(text);
    }, DELAY);

    return () => clearTimeout(timer);
  }, [text, reported, onValueChange]);

  return (
    <Input
      classNames={{ ...classNames, inputWrapper: `${FILTER_H} ${classNames?.inputWrapper ?? ""}` }}
      {...props}
      value={text}
      onClear={() => {
        setText("");
        setReported("");
        if (onClear) onClear();
        else onValueChange?.("");
      }}
      onValueChange={setText}
    />
  );
}
