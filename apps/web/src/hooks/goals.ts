"use client";

import { useQuery } from "@tanstack/react-query";

import { useMe } from "./queries";

import { api } from "@/lib/api";
import type { AcademyGoal, Goal, Note } from "@/lib/goals";

export const ACADEMY_GOAL_KEY = ["academy-goal"] as const;

export function useIsSuperadmin(): boolean {
  const { data: me } = useMe();

  return me?.role.code === "superadmin";
}

export function useAcademyGoal() {
  return useQuery({
    queryKey: ACADEMY_GOAL_KEY,
    queryFn: () => api<AcademyGoal>("/api/v1/academy/goal"),
    staleTime: 60_000,
  });
}

export function useGoals(archived = false) {
  return useQuery({
    queryKey: ["goals", { archived }],
    queryFn: () => api<{ items: Goal[] }>("/api/v1/goals", { params: { archived: archived ? "true" : undefined } }),
  });
}

export type NoteFilter = { goal_id?: string; course_id?: string; cohort_id?: string; q?: string; limit?: number };

export function useNotes(filter: NoteFilter = {}, enabled = true) {
  return useQuery({
    queryKey: ["notes", filter],
    queryFn: () =>
      api<{ items: Note[] }>("/api/v1/notes", {
        params: { ...filter, limit: filter.limit ? String(filter.limit) : undefined },
      }),
    enabled,
  });
}
