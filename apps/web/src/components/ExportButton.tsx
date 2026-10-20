"use client";

import { useState } from "react";

import { Icon } from "./Icon";
import { LoadingButton } from "./LoadingButton";

import { downloadExport } from "@/lib/api";
import { notifyError } from "@/lib/toast";

/**
 * The one «Excel» button of every table. `path` is the list's export endpoint
 * (`/api/v1/students/export`), `params` the filters the list currently uses: the API builds the
 * file from the same query, so the sheet always equals the screen (all pages, not just this one).
 * On a phone it shrinks to the icon so it fits the toolbar.
 */
export function ExportButton({
  path,
  params,
  label = "Excel",
}: {
  path: string;
  params?: Record<string, string | null | undefined>;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await downloadExport(path, Object.fromEntries(Object.entries(params ?? {}).map(([k, v]) => [k, v ?? undefined])));
    } catch (e) {
      notifyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <LoadingButton
        aria-label={`${label}: скачать таблицу`}
        className="hidden md:inline-flex"
        isLoading={busy}
        startContent={<Icon name="download" size={18} />}
        variant="flat"
        onPress={() => void run()}
      >
        {label}
      </LoadingButton>
      <LoadingButton
        isIconOnly
        aria-label={`${label}: скачать таблицу`}
        className="md:hidden"
        isLoading={busy}
        variant="flat"
        onPress={() => void run()}
      >
        <Icon name="download" size={18} />
      </LoadingButton>
    </>
  );
}
