"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";


import { PayoutsList, ScheduleList, salaryStats } from "./parts";

import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { ListSkeleton } from "@/components/Skeletons";
import { StatCards, StatCardsSkeleton } from "@/components/StatCards";
import { useCanPaySalaries } from "@/hooks/money";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { monthOf, monthOptions } from "@/lib/money";
import { todayIso } from "@/lib/education";
import type { InstructorCard, PayoutsPage, SalaryData, SalaryRow } from "@/lib/money-types";
import { lazyModal } from "@/lib/lazy-modal";

const RateModal = lazyModal(() => import("../instructors/RateModal").then((m) => m.RateModal));
const PayoutModal = lazyModal(() => import("./PayoutModal").then((m) => m.PayoutModal));

type Tab = "schedule" | "payouts";
const PAGE_SIZE = 25;

export default function SalariesPage() {
  const canPay = useCanPaySalaries();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const current = monthOf(todayIso());
  const [tab, setTab] = useState<Tab>("schedule");
  const [month, setMonth] = useState<string>(current);
  const [instructor, setInstructor] = useState<string | null>(null);
  const [branch, setBranch] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [paying, setPaying] = useState<SalaryRow | null>(null);
  const [rating, setRating] = useState<SalaryRow | null>(null);

  const instructors = useQuery({
    queryKey: ["instructor-cards", ""],
    queryFn: () => api<{ items: InstructorCard[]; total: number }>("/api/v1/instructors"),
  });
  const filters = {
    instructor_id: instructor ?? undefined,
    branch_id: branch ?? undefined,
  };
  const schedule = useQuery({
    queryKey: ["salaries", month, instructor, branch],
    queryFn: () => api<SalaryData>("/api/v1/salaries", { params: { ...filters, month } }),
    enabled: tab === "schedule",
  });
  const summary = useQuery({
    queryKey: ["salaries", "summary", instructor, branch],
    queryFn: () => api<SalaryData>("/api/v1/salaries", { params: { ...filters, month: current } }),
  });
  const payouts = useQuery({
    queryKey: ["payouts", month, instructor, branch, page],
    queryFn: () =>
      api<PayoutsPage>("/api/v1/payouts", {
        params: { ...filters, month: month === "all" ? undefined : month, page: String(page), page_size: String(PAGE_SIZE) },
      }),
    enabled: tab === "payouts",
  });

  const reset = () => setPage(1);
  const filtered = month !== current || !!instructor || !!branch;

  return (
    <>
      <PageHeader
        actions={
          <ExportButton
            params={{ ...filters, month: tab === "schedule" ? month : month === "all" ? undefined : month }}
            path={tab === "schedule" ? "/api/v1/salaries/export" : "/api/v1/payouts/export"}
          />
        }
        title="Зарплаты"
      />

      {summary.data ? <StatCards stats={salaryStats(summary.data.summary)} /> : <StatCardsSkeleton count={4} />}

      <Segmented
        className="mb-4"
        label="Раздел зарплат"
        options={[
          { key: "schedule", label: "График выплат" },
          { key: "payouts", label: "Выплаты" },
        ]}
        value={tab}
        onChange={(t) => {
          setTab(t);
          reset();
          // payouts are made after the month: the current month alone looks empty
          if (t === "payouts" && month === current) setMonth("all");
        }}
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 md:flex md:flex-wrap">
        <SelectField
          className="md:w-52"
          label="Месяц"
          options={[{ key: "all", label: "Все месяцы" }, ...monthOptions(current, 12, 12)]}
          value={month}
          onChange={(m) => {
            setMonth(m ?? current);
            reset();
          }}
        />
        <SelectField
          allLabel="Все инструкторы"
          className="md:w-56"
          label="Инструктор"
          options={(instructors.data?.items ?? []).map((i) => ({ key: i.id, label: i.full_name }))}
          value={instructor}
          onChange={(i) => {
            setInstructor(i);
            reset();
          }}
        />
        {!me?.branch && (
          <SelectField
            allLabel="Все филиалы"
            className="md:w-48"
            label="Филиал"
            options={branches.map((b) => ({ key: b.id, label: b.name }))}
            value={branch}
            onChange={(b) => {
              setBranch(b);
              reset();
            }}
          />
        )}
      </div>

      {tab === "schedule" ? (
        <QueryState
          empty={
            <EmptyState
              hint="Расписание выплат строится по потокам с инструктором."
              title={filtered ? "В графике ничего не найдено" : "В этом месяце выплат нет"}
            />
          }
          isEmpty={(d) => d.items.length === 0}
          query={schedule}
          skeleton={<ListSkeleton cols={8} />}
        >
          {(d) => (
            <ScheduleList actions={canPay ? { onPay: setPaying, onRate: setRating } : undefined} rows={d.items} />
          )}
        </QueryState>
      ) : (
        <QueryState
          empty={<EmptyState title="Выплат не найдено" />}
          isEmpty={(d) => d.items.length === 0}
          query={payouts}
          skeleton={<ListSkeleton cols={7} />}
        >
          {(d) => (
            <>
              <PayoutsList rows={d.items} />
              <Pager page={page} pageSize={PAGE_SIZE} total={d.total} onChange={setPage} />
            </>
          )}
        </QueryState>
      )}

      {paying && <PayoutModal row={paying} onClose={() => setPaying(null)} />}
      {rating && (
        <RateModal
          field="instructor_rate"
          hint="Сколько инструктор получает за каждый месяц этого потока."
          record={{ version: rating.cohort_version, instructor_rate: rating.rate }}
          request={(rate, version) =>
            api(`/api/v1/salaries/cohorts/${rating.cohort_id}/rate`, { method: "PATCH", body: { instructor_rate: rate }, version })
          }
          title={`Ставка потока ${rating.cohort_code}`}
          onClose={() => setRating(null)}
        />
      )}
    </>
  );
}
