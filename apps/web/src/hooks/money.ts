"use client";

import { useQueryClient } from "@tanstack/react-query";

import { useMe } from "./queries";

import { can } from "@/lib/permissions";

/** Money of students: the `payments` section, never for the instructor role (the API says 403). */
export function useSeesPayments(): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, "payments", "view");
}

export function useCanPay(): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, "payments", "change");
}

/** Salaries and instructors: the `instructors` section; the instructor role only reads its own. */
export function useCanPaySalaries(): boolean {
  const { data: me } = useMe();

  return !!me && me.role.code !== "instructor" && can(me.permissions, "instructors", "change");
}

const MONEY_KEYS = ["payments", "debtors", "cohort-payments", "pay-options", "salaries", "payouts", "instructor-cards", "instructor-detail"];

/** A payment, a payout or a rate changes lists, sums and cards: mark them all stale. */
export function useRefreshMoney() {
  const queryClient = useQueryClient();

  return () => queryClient.invalidateQueries({ predicate: (q) => MONEY_KEYS.includes(String(q.queryKey[0])) });
}
