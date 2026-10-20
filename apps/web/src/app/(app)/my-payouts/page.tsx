"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PayoutsList, ScheduleList, salaryStats } from "../salaries/parts";

import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { ListSkeleton } from "@/components/Skeletons";
import { StatCards, StatCardsSkeleton } from "@/components/StatCards";
import { useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/education";
import type { InstructorDetail, PayoutsPage, SalaryData } from "@/lib/money-types";

type Tab = "schedule" | "payouts";
const PAGE_SIZE = 25;

/** The instructor's own money: rate, schedule, payouts. The API returns nothing of anybody else. */
export default function MyPayoutsPage() {
  const { data: me } = useMe();
  const [tab, setTab] = useState<Tab>("schedule");
  const [page, setPage] = useState(1);

  const card = useQuery({
    queryKey: ["instructor-detail", me?.id],
    queryFn: () => api<InstructorDetail>(`/api/v1/instructors/${me?.id}`),
    enabled: !!me,
  });
  const schedule = useQuery({
    queryKey: ["salaries", "mine"],
    queryFn: () => api<SalaryData>("/api/v1/salaries", { params: { month: "all" } }),
  });
  const payouts = useQuery({
    queryKey: ["payouts", "mine", page],
    queryFn: () => api<PayoutsPage>("/api/v1/payouts", { params: { page: String(page), page_size: String(PAGE_SIZE) } }),
    enabled: tab === "payouts",
  });

  return (
    <>
      <PageHeader
        actions={<ExportButton path={tab === "schedule" ? "/api/v1/salaries/export" : "/api/v1/payouts/export"} params={tab === "schedule" ? { month: "all" } : {}} />}
        title="Мои выплаты"
      />

      {schedule.data ? (
        <StatCards stats={salaryStats(schedule.data.summary)} />
      ) : (
        <StatCardsSkeleton count={4} />
      )}
      {card.data && (
        <p className="mb-4 text-sm text-default-600">
          Моя ставка по умолчанию: <b>{formatPrice(card.data.default_rate)}</b> в месяц
        </p>
      )}

      <Segmented
        className="mb-4"
        label="Мои выплаты"
        options={[
          { key: "schedule", label: "График" },
          { key: "payouts", label: "Полученные" },
        ]}
        value={tab}
        onChange={(t) => {
          setTab(t);
          setPage(1);
        }}
      />

      {tab === "schedule" ? (
        <QueryState
          empty={<EmptyState title="Пока нет потоков с выплатами" />}
          isEmpty={(d) => d.items.length === 0}
          query={schedule}
          skeleton={<ListSkeleton cols={6} />}
        >
          {(d) => <ScheduleList rows={d.items} showInstructor={false} />}
        </QueryState>
      ) : (
        <QueryState
          empty={<EmptyState title="Выплат ещё не было" />}
          isEmpty={(d) => d.items.length === 0}
          query={payouts}
          skeleton={<ListSkeleton cols={6} />}
        >
          {(d) => (
            <>
              <PayoutsList rows={d.items} showInstructor={false} />
              <Pager page={page} pageSize={PAGE_SIZE} total={d.total} onChange={setPage} />
            </>
          )}
        </QueryState>
      )}
    </>
  );
}
