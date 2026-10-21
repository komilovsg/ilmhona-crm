import type { ReactNode } from "react";

import { IlmMark } from "./brand/IlmMark";

/**
 * The look of 404 and the error boundary: brand mark, a quiet big code, title, text, actions.
 * `inShell`: sits in the page area of the app shell; otherwise it fills the screen.
 */
export function ErrorScreen({
  code,
  title,
  text,
  codeLabel,
  actions,
  inShell = false,
}: {
  code?: string | null;
  title: string;
  text: string;
  codeLabel?: string;
  actions: ReactNode;
  inShell?: boolean;
}) {
  return (
    <div
      className={`err-in flex flex-col items-center justify-center px-4 text-center ${inShell ? "min-h-[60dvh] py-10" : "min-h-dvh py-16"}`}
      role={codeLabel ? "alert" : undefined}
    >
      <span className="mb-6 rounded-2xl bg-primary/10 p-4 text-brand-text">
        <IlmMark height={36} />
      </span>
      {code && !codeLabel && <p className="mb-1 text-6xl font-bold tracking-tight text-default-300">{code}</p>}
      <h1 className="text-xl font-semibold sm:text-2xl">{title}</h1>
      <p className="mt-2 max-w-md text-sm text-default-500">{text}</p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">{actions}</div>
      {code && codeLabel && (
        <p className="mt-6 text-xs text-default-500">
          {codeLabel}: <span className="select-all font-mono">{code}</span>
        </p>
      )}
    </div>
  );
}
