"use client";

import { Button } from "@heroui/button";
import Link from "next/link";
import { useEffect } from "react";

import { ErrorScreen } from "@/components/ErrorScreen";
import { ERROR_COPY, errorCode } from "@/lib/error-copy";

const copy = ERROR_COPY.failure;

/** A page threw while rendering: the shell stays, the page area offers «Повторить». No message or stack is shown. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <ErrorScreen
      actions={
        <>
          <Button color="primary" onPress={reset}>
            {copy.retry}
          </Button>
          <Button as={Link} href="/" variant="flat">
            {copy.home}
          </Button>
        </>
      }
      code={errorCode(error) ?? "—"}
      codeLabel={copy.codeLabel}
      inShell
      text={copy.text}
      title={copy.title}
    />
  );
}
