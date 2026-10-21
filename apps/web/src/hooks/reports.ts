"use client";

import { useQueryClient } from "@tanstack/react-query";

import { useMe } from "./queries";

import { can } from "@/lib/permissions";

/** Graduates, certificates and employment never open for the instructor role (the API says 403). */
export function useCanChangeGraduates(): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, "graduates", "change");
}

export function useCanSeeGraduates(): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, "graduates", "view");
}

const REPORT_KEYS = ["graduates", "graduate-courses", "employment", "master-list", "dashboard", "student", "students", "cohort"];

/** A certificate or an employment write changes every report that reads them: mark all stale. */
export function useRefreshReports() {
  const queryClient = useQueryClient();

  return () => queryClient.invalidateQueries({ predicate: (q) => REPORT_KEYS.includes(String(q.queryKey[0])) });
}
