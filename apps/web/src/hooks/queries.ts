"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { takeEarlyMe } from "@/lib/early-me";
import type { Branch, Me, ResetRequestRow, RoleRow, SectionInfo } from "@/lib/types";

export const ME_KEY = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => (((await takeEarlyMe()) as Me | null) ?? api<Me>("/api/v1/auth/me")),
    staleTime: 60_000,
  });
}

export function useBranches() {
  return useQuery({
    queryKey: ["branches"],
    queryFn: () => api<Branch[]>("/api/v1/branches"),
    staleTime: 5 * 60_000,
  });
}

export function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: () => api<RoleRow[]>("/api/v1/roles") });
}

export function useSections() {
  return useQuery({
    queryKey: ["sections"],
    queryFn: () => api<SectionInfo[]>("/api/v1/roles/sections"),
    staleTime: Infinity,
  });
}

export const RESET_REQUESTS_KEY = ["reset-requests"] as const;

/** Open «forgot password» requests: only asked for by users who may act on them. */
export function useResetRequests(enabled: boolean) {
  return useQuery({
    queryKey: RESET_REQUESTS_KEY,
    queryFn: () => api<{ items: ResetRequestRow[]; total: number }>("/api/v1/users/reset-requests"),
    enabled,
    refetchInterval: 60_000,
  });
}
