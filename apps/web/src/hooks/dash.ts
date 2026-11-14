"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Layout } from "@/lib/dash";

export const LAYOUT_KEY = ["dashboard", "layout"] as const;
export const LAYOUT_PATH = "/api/v1/me/preferences/dashboard";

export function useDashLayout() {
  return useQuery({ queryKey: LAYOUT_KEY, queryFn: () => api<Layout>(LAYOUT_PATH), staleTime: 60_000 });
}

/**
 * The data of one dashboard card: its own endpoint and query. A card the layout hides is never
 * rendered, so its query never runs. `branch` is the page's branch toggle ("all" = no filter).
 */
export function useCard<T>(name: string, branch: string) {
  const branch_id = branch === "all" ? undefined : branch;

  return useQuery({
    queryKey: ["dashboard", "card", name, branch_id ?? "all"],
    queryFn: () => api<T>(`/api/v1/dashboard/cards/${name}`, { params: { branch_id } }),
    placeholderData: keepPreviousData,
  });
}
