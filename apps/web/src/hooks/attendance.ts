"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useMe } from "./queries";

import { api } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { TodayData } from "@/lib/types";

/**
 * May the user mark attendance and grade? Unlike `useCanChange`, the instructor role counts: it
 * is the one write an instructor has (own cohorts only, the API enforces that).
 */
export function useCanMark(): boolean {
  const { data: me } = useMe();

  return !!me && can(me.permissions, "attendance", "change");
}

export function useCanSeeAttendance(): boolean {
  const { data: me } = useMe();

  return !!me && can(me.permissions, "attendance", "view");
}

export function useToday(enabled = true) {
  return useQuery({
    queryKey: ["today"],
    queryFn: () => api<TodayData>("/api/v1/me/today"),
    enabled,
  });
}

const KEYS = ["today", "grid", "grades"];

/** A mark or a grade changes the home screen, the grid and the grades: mark them stale. */
export function useRefreshAttendance() {
  const queryClient = useQueryClient();

  return () => queryClient.invalidateQueries({ predicate: (q) => KEYS.includes(String(q.queryKey[0])) });
}
