"use client";

import { useState } from "react";
import { Input, type InputProps } from "@heroui/input";

import { Icon } from "./Icon";

/** Password input with a show/hide button. */
export function PasswordField(props: Omit<InputProps, "type" | "endContent">) {
  const [shown, setShown] = useState(false);
  const [caps, setCaps] = useState(false);

  return (
    <Input
      {...props}
      description={caps ? "Включён Caps Lock" : props.description}
      onBlur={(e) => {
        setCaps(false);
        props.onBlur?.(e);
      }}
      onKeyUp={(e) => {
        setCaps(e.getModifierState("CapsLock"));
        props.onKeyUp?.(e);
      }}
      endContent={
        <button
          aria-label={shown ? "Скрыть пароль" : "Показать пароль"}
          className="text-default-500"
          type="button"
          onClick={() => setShown((s) => !s)}
        >
          <Icon name={shown ? "ban" : "eye"} size={18} />
        </button>
      }
      type={shown ? "text" : "password"}
    />
  );
}
