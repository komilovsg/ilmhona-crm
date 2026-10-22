"use client";

import { Button } from "@heroui/button";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ErrorScreen } from "./ErrorScreen";

import { ERROR_COPY } from "@/lib/error-copy";

const copy = ERROR_COPY.notFound;

export function NotFoundScreen({ inShell = false }: { inShell?: boolean }) {
  const router = useRouter();
  return (
    <ErrorScreen
      actions={
        <>
          <Button as={Link} color="primary" href="/">
            {copy.home}
          </Button>
          <Button variant="flat" onPress={() => (window.history.length > 1 ? router.back() : router.push("/"))}>
            {copy.back}
          </Button>
        </>
      }
      code={copy.code}
      inShell={inShell}
      text={copy.text}
      title={copy.title}
    />
  );
}
