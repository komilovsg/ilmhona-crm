"use client";

import { useQueryClient } from "@tanstack/react-query";

import { useMe } from "./queries";

import { can } from "@/lib/permissions";

/** Leads and campaigns never open for the instructor role (the API says 403 whatever the matrix). */
export function useCanChangeSales(section: "leads" | "marketing"): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, section, "change");
}

const SALES_KEYS = ["leads", "lead-funnel", "campaigns"];

/** A lead or campaign write changes the lists, the funnel and the CPL / CAC: mark them all stale. */
export function useRefreshSales() {
  const queryClient = useQueryClient();

  return () => queryClient.invalidateQueries({ predicate: (q) => SALES_KEYS.includes(String(q.queryKey[0])) });
}
