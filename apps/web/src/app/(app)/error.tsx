"use client";

import { Button } from "@heroui/button";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect } from "react";

import { ErrorScreen } from "@/components/ErrorScreen";
import { ERROR_COPY, supportCode } from "@/lib/error-copy";
import { reportError } from "@/lib/report-error";

const copy = ERROR_COPY.failure;

/** A page threw while rendering: the shell stays, the page area offers «Повторить». No message or stack is shown. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const queryClient = useQueryClient();

  useEffect(() => {
    console.error(error);
    reportError(error);
  }, [error]);

  // the cached data may be what broke the page: drop it, so the retry loads fresh data
  const retry = () => {
    queryClient.removeQueries();
    reset();
  };

  return (
    <ErrorScreen
      actions={
        <>
          <Button color="primary" onPress={retry}>
            {copy.retry}
          </Button>
          <Button as={Link} href="/" variant="flat">
            {copy.home}
          </Button>
        </>
      }
      code={supportCode(error)}
      codeLabel={copy.codeLabel}
      inShell
      text={copy.text}
      title={copy.title}
    />
  );
}
