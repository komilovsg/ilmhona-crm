"use client";

import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { LoadingButton } from "./LoadingButton";
import { Late } from "./Skeletons";

import { isApiError } from "@/lib/api";

/** Nothing to show yet: «Нет студентов» + the way to add one, when the user may. */
export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-content1 p-8 text-center">
      <p className="font-medium">{title}</p>
      {hint && <p className="text-sm text-default-500">{hint}</p>}
      {action}
    </div>
  );
}

/** The request failed: say so and offer «Повторить» (never an endless skeleton). */
export function ErrorState({
  onRetry,
  text = "Не удалось загрузить",
  retrying = false,
}: {
  onRetry: () => void;
  text?: string;
  retrying?: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl bg-content1 p-8 text-center" role="alert">
      <p className="font-medium">{text}</p>
      <p className="text-sm text-default-500">Проверьте связь с сервером и попробуйте ещё раз.</p>
      <LoadingButton color="primary" isLoading={retrying} variant="flat" onPress={onRetry}>
        Повторить
      </LoadingButton>
    </div>
  );
}

/**
 * The four states of a request, the same on every page:
 * - loading: the shape-matched `skeleton`, shown only after ~300 ms, its space reserved at once;
 * - error: «Не удалось загрузить» + «Повторить» (a 404 shows `notFound` when given);
 * - empty: `empty` (use `EmptyState`);
 * - ready: `children`. A refetch keeps the old data on screen (`aria-busy`, the thin top bar in AppShell).
 */
export function QueryState<T>({
  query,
  skeleton,
  isEmpty,
  empty,
  notFound,
  errorText,
  children,
}: {
  query: UseQueryResult<T>;
  skeleton: ReactNode;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  notFound?: ReactNode;
  errorText?: string;
  children: ReactNode | ((data: T) => ReactNode);
}) {
  const { data, isPending, isError, error, isFetching, refetch } = query;

  if (isPending && !isError)
    return (
      <div aria-busy="true" role="status">
        <span className="sr-only">Загрузка…</span>
        <Late>{skeleton}</Late>
      </div>
    );

  if (data === undefined) {
    if (notFound && isApiError(error) && error.status === 404) return <>{notFound}</>;

    return <ErrorState retrying={isFetching} text={errorText} onRetry={() => void refetch()} />;
  }

  if (isEmpty?.(data) && empty) return <div aria-busy={isFetching}>{empty}</div>;

  return (
    <div aria-busy={isFetching}>
      {isError && (
        <p className="mb-3 flex flex-wrap items-center gap-2 rounded-xl bg-warning/10 px-4 py-2 text-sm" role="alert">
          Не удалось обновить данные.
          <button className="text-brand-text underline" type="button" onClick={() => void refetch()}>
            Повторить
          </button>
        </p>
      )}
      {typeof children === "function" ? children(data) : children}
    </div>
  );
}
