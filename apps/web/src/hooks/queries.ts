"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Branch, Me, RoleRow, SectionInfo } from "@/lib/types";

export const ME_KEY = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: ME_KEY, queryFn: () => api<Me>("/api/v1/auth/me"), staleTime: 60_000 });
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
