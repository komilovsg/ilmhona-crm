import { redirect } from "next/navigation";

import { CodeForm } from "./CodeForm";

import { normalizeCode } from "@/lib/verify";

/** The check page without a code: the form. `?code=` (the form, no JavaScript needed) opens /v/<code>. */
export default async function VerifyHome({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const raw = (await searchParams).code;
  const typed = typeof raw === "string" ? raw.trim() : "";
  if (typed) redirect(`/v/${encodeURIComponent(normalizeCode(typed) ?? typed.slice(0, 20))}`);
  return (
    <>
      <h1 className="mb-2 font-display text-2xl font-semibold tracking-tight sm:text-3xl">Проверка сертификата</h1>
      <p className="mb-6 text-default-500">Отсканируйте QR-код на сертификате или введите код вручную.</p>
      <CodeForm title="Код сертификата" />
    </>
  );
}
