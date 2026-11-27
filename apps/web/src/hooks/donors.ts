"use client";

import { useQuery } from "@tanstack/react-query";

import { useMe } from "./queries";

import { api } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { DonorRef } from "@/lib/types";

/** Every donor by name (archived last): the choices of the cohort form and the filters. */
export function useDonorOptions(enabled = true) {
  return useQuery({
    queryKey: ["donors", "options"],
    queryFn: () => api<DonorRef[]>("/api/v1/donors/options"),
    enabled,
  });
}

export function useCanSeeDonors(): boolean {
  const { data: me } = useMe();

  return !!me && can(me.permissions, "donors", "view");
}
