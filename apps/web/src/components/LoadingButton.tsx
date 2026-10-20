"use client";

import { Button, type ButtonProps } from "@heroui/button";
import { Spinner } from "@heroui/spinner";
import clsx from "clsx";

/**
 * A button that shows a spinner inside itself while `isLoading` and keeps its width: the label
 * stays in the layout (invisible) and the spinner is centred over it, so the button never jumps.
 */
export function LoadingButton({ isLoading = false, children, startContent, endContent, className, ...props }: ButtonProps) {
  return (
    <Button
      {...props}
      aria-busy={isLoading}
      className={clsx("relative", className)}
      isDisabled={props.isDisabled || isLoading}
    >
      <span className={clsx("inline-flex items-center gap-2", isLoading && "invisible")}>
        {startContent}
        {children}
        {endContent}
      </span>
      {isLoading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner color="current" size="sm" />
        </span>
      )}
    </Button>
  );
}
