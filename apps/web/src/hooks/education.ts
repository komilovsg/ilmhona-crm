"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useMe } from "./queries";

import { api } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { Course, EducationSummary, Room } from "@/lib/types";

export type InstructorOption = { id: string; full_name: string; branch_id: string | null };

/**
 * May the user create / edit in `section`? The instructor role never writes (the API says 403
 * anyway; the controls are hidden so nobody meets the error).
 */
export function useCanChange(section: string): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, section, "change");
}

export function useRooms(branchId?: string | null) {
  return useQuery({
    queryKey: ["rooms", branchId ?? null],
    queryFn: () => api<Room[]>("/api/v1/rooms", { params: { branch_id: branchId ?? undefined } }),
  });
}

export function useCourses() {
  return useQuery({ queryKey: ["courses"], queryFn: () => api<Course[]>("/api/v1/courses") });
}

export function useInstructors(branchId?: string | null) {
  return useQuery({
    queryKey: ["instructors", branchId ?? null],
    queryFn: () =>
      api<InstructorOption[]>("/api/v1/cohorts/instructors", { params: { branch_id: branchId ?? undefined } }),
  });
}

export function useEducationSummary() {
  return useQuery({
    queryKey: ["summary"],
    queryFn: () => api<EducationSummary>("/api/v1/metrics/education"),
  });
}

const EDUCATION_KEYS = [
  "rooms",
  "courses",
  "instructors",
  "summary",
  "schedule",
  "cohorts",
  "cohort",
  "lessons",
  "enrollments",
  "students",
  "student",
];

/** Any write may change the lists, the cards and the numbers: refetch all of them. */
export function useRefreshEducation() {
  const queryClient = useQueryClient();

  return () =>
    queryClient.invalidateQueries({
      predicate: (q) => EDUCATION_KEYS.includes(String(q.queryKey[0])),
    });
}
