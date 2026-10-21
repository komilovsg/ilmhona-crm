"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Input } from "@heroui/input";

import { BarList } from "@/components/charts/BarList";
import { TrendChart } from "@/components/charts/TrendChart";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { Bone } from "@/components/Skeletons";
import { type Stat, StatCards, StatCardsSkeleton } from "@/components/StatCards";
import { useBranches, useMe } from "@/hooks/queries";
import { can } from "@/lib/permissions";
import { api } from "@/lib/api";
import { dayTitle, formatPrice } from "@/lib/education";
import { formatDateTime } from "@/lib/format";
import { compact, orDash, shortMonth } from "@/lib/reports";
import type { CourseRow, LeadItem, MonthRow, Overview } from "@/lib/reports-types";
import { LEAD_STATUSES, percentLabel } from "@/lib/sales";
import { monthLabel } from "@/lib/money";

type Tab = "overview" | "months" | "courses";
const TABS = [
  { key: "overview", label: "Обзор" },
  { key: "months", label: "По месяцам" },
  { key: "courses", label: "По курсам" },
] as const;

const money = (n: number) => formatPrice(n);

function Widget({ title, count, children, empty }: { title: string; count?: number; children: React.ReactNode; empty: string }) {
  return (
    <section aria-label={title} className="rounded-2xl bg-content1 p-4">
      <h2 className="mb-2 flex items-baseline justify-between text-sm font-medium">
        {title}
        {count !== undefined && <span className="text-xs font-normal text-default-500">{count}</span>}
      </h2>
      {count === 0 ? <p className="py-4 text-center text-sm text-default-500">{empty}</p> : children}
    </section>
  );
}

function LeadList({ items, when }: { items: LeadItem[]; when: "created" | "callback" }) {
  return (
    <ul>
      {items.map((l) => (
        <li key={l.id}>
          <Link className="flex min-h-12 items-center justify-between gap-3 rounded-xl px-2 py-1.5 hover:bg-default-100" href={`/leads?q=${encodeURIComponent(l.full_name)}`}>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{l.full_name}</span>
              <span className="block truncate text-xs text-default-500">{[l.course_name, l.status].filter(Boolean).join(" · ")}</span>
            </span>
            <span className="shrink-0 text-xs text-default-500">{formatDateTime(when === "callback" ? l.next_contact_at : l.created_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function OverviewTab({ data, leads }: { data: Overview; leads: boolean }) {
  const total = data.funnel["всего"] ?? 0;
  const funnel = LEAD_STATUSES.map((s) => ({
    key: s,
    label: s[0].toUpperCase() + s.slice(1),
    value: data.funnel[s] ?? 0,
    text: String(data.funnel[s] ?? 0),
    hint: total ? percentLabel(Math.round(((data.funnel[s] ?? 0) * 1000) / total) / 10) : undefined,
  }));

  return (
    <>
      <StatCards
        stats={([
          { label: "Лиды", value: String(data.leads), hint: `Конверсия: ${percentLabel(data.conversion)}` },
          { label: "Активные студенты", value: String(data.active_students), hint: `Всего в базе: ${data.students_total}` },
          data.income != null && { label: "Оплачено", value: formatPrice(data.income), hint: "Подтверждённые оплаты" },
          { label: "Активные потоки", value: String(data.active_cohorts), hint: `На наборе: ${data.recruiting_cohorts}` },
          data.payroll != null && { label: "Расходы на ЗП", value: formatPrice(data.payroll), hint: "Фактические выплаты" },
          data.profit != null && {
            label: "Прибыль",
            value: formatPrice(data.profit),
            hint: "Доход − реклама − ЗП",
            tone: Number(data.profit) < 0 ? ("danger" as const) : ("success" as const),
          },
          data.ads != null && { label: "Реклама", value: formatPrice(data.ads), hint: `Кампаний: ${data.campaigns}` },
          { label: "Выпускники", value: String(data.graduates), hint: "Балл 70 и выше" },
          data.ads != null && { label: "CAC", value: orDash(data.cac, formatPrice), hint: "Реклама ÷ записавшиеся" },
        ] as (Stat | false)[]).filter((s): s is Stat => !!s)}
      />
      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <BarList note="доля от всех лидов периода" rows={funnel} title="Воронка лидов" />
        <Widget count={data.unfilled.count} empty="Всё заполнено" title="Не заполнено">
          <ul>
            {data.unfilled.items.map((u) => (
              <li key={`${u.lesson_id}`}>
                <Link className="flex min-h-12 items-center justify-between gap-3 rounded-xl px-2 py-1.5 hover:bg-default-100" href={`/lessons/${u.lesson_id}`}>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {dayTitle(u.date)} · {u.course_name}
                    </span>
                    <span className="block text-xs text-default-500">{u.cohort_code}</span>
                  </span>
                  <span className="shrink-0 text-xs text-default-500 tabular-nums">
                    {u.marked}/{u.total}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Widget>
      </div>
      {leads && <div className="grid gap-4 lg:grid-cols-2">
        <Widget count={data.callbacks.count} empty="Звонков на сегодня нет" title="Перезвонить сегодня">
          <LeadList items={data.callbacks.items} when="callback" />
        </Widget>
        <Widget count={data.recent_leads.length} empty="Лидов пока нет" title="Последние лиды">
          <LeadList items={data.recent_leads} when="created" />
        </Widget>
      </div>}
    </>
  );
}

type MoneyKey = "income" | "payroll" | "ads" | "profit";

function MonthsTab({ items }: { items: MonthRow[] }) {
  const labels = items.map((m) => shortMonth(m.month));
  const full = items.map((m) => monthLabel(m.month));
  const num = (key: MoneyKey) => items.map((m) => Number(m[key]));
  const anyMoney = items.some((m) => m.income != null || m.payroll != null || m.ads != null);

  return (
    <div className="grid gap-4">
      {anyMoney && <TrendChart
        fullLabels={full}
        format={money}
        labels={labels}
        series={[
          { key: "income", label: "Доход", color: "var(--series-1)", values: num("income") },
          { key: "payroll", label: "Зарплата", color: "var(--series-2)", values: num("payroll") },
          { key: "ads", label: "Реклама", color: "var(--series-3)", values: num("ads") },
          { key: "profit", label: "Прибыль", color: "var(--series-4)", values: num("profit") },
        ].filter((s) => items.some((m) => m[s.key as MoneyKey] != null))}
        title="Деньги по месяцам, TJS"
      />}
      <TrendChart
        fullLabels={full}
        format={(n) => String(n)}
        labels={labels}
        series={[
          { key: "leads", label: "Лиды", color: "var(--series-1)", values: items.map((m) => m.leads) },
          { key: "students", label: "Новые студенты", color: "var(--series-4)", values: items.map((m) => m.new_students) },
        ]}
        title="Лиды и новые студенты по месяцам"
      />
    </div>
  );
}

function CoursesTab({ items }: { items: CourseRow[] }) {
  const by = (pick: (c: CourseRow) => number, text: (c: CourseRow) => string) =>
    [...items]
      .sort((a, b) => pick(b) - pick(a) || a.course_name.localeCompare(b.course_name, "ru"))
      .map((c) => ({ key: c.course_id, label: c.course_name, value: pick(c), text: text(c), hint: c.graduates ? `· выпускников ${c.graduates}` : undefined }));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {items.some((c) => c.income != null) && (
        <BarList rows={by((c) => Number(c.income), (c) => `${compact(Number(c.income))} TJS`)} title="Доход по курсам" />
      )}
      <BarList rows={by((c) => c.students, (c) => String(c.students))} title="Студенты по курсам" />
    </div>
  );
}

export default function DashboardPage() {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const [tab, setTab] = useState<Tab>("overview");
  const [branch, setBranch] = useState<string>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const params = { branch_id: branch === "all" ? undefined : branch, date_from: from || undefined, date_to: to || undefined };
  const shown = me?.branch ? branches.filter((b) => b.id === me.branch?.id) : branches;

  const overview = useQuery({
    queryKey: ["dashboard", "overview", params],
    queryFn: () => api<Overview>("/api/v1/dashboard/overview", { params }),
    placeholderData: keepPreviousData,
    enabled: tab === "overview",
  });
  const months = useQuery({
    queryKey: ["dashboard", "months", params.branch_id],
    queryFn: () => api<{ items: MonthRow[] }>("/api/v1/dashboard/by-month", { params: { branch_id: params.branch_id } }),
    placeholderData: keepPreviousData,
    enabled: tab === "months",
  });
  const courses = useQuery({
    queryKey: ["dashboard", "courses", params],
    queryFn: () => api<{ items: CourseRow[] }>("/api/v1/dashboard/by-course", { params }),
    placeholderData: keepPreviousData,
    enabled: tab === "courses",
  });
  const chartSkeleton = <Bone className="h-72 w-full rounded-2xl" />;

  return (
    <>
      <PageHeader
        actions={tab === "months" ? <ExportButton params={{ branch_id: params.branch_id }} path="/api/v1/dashboard/by-month/export" /> : undefined}
        title="Дашборд"
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Segmented label="Раздел дашборда" options={[...TABS]} value={tab} onChange={setTab} />
        {(!me?.branch || shown.length > 1) && (
          <Segmented
            label="Филиал"
            options={[{ key: "all", label: "Все" }, ...shown.map((b) => ({ key: b.id, label: b.name }))]}
            value={branch}
            onChange={setBranch}
          />
        )}
        {tab !== "months" && (
          <div className="flex gap-2">
            <Input className="w-40" label="С" size="sm" type="date" value={from} onValueChange={setFrom} />
            <Input className="w-40" label="По" size="sm" type="date" value={to} onValueChange={setTo} />
          </div>
        )}
      </div>
      {tab === "overview" && (
        <QueryState
          query={overview}
          skeleton={
            <>
              <StatCardsSkeleton count={3} />
              <StatCardsSkeleton count={3} />
              <StatCardsSkeleton count={3} />
              <div className="grid gap-4 lg:grid-cols-2">{chartSkeleton}{chartSkeleton}</div>
            </>
          }
        >
          {(data) => <OverviewTab data={data} leads={can(me?.permissions, "leads")} />}
        </QueryState>
      )}
      {tab === "months" && (
        <QueryState query={months} skeleton={<div className="grid gap-4">{chartSkeleton}{chartSkeleton}</div>}>
          {(data) => <MonthsTab items={data.items} />}
        </QueryState>
      )}
      {tab === "courses" && (
        <QueryState
          isEmpty={(d) => d.items.length === 0}
          empty={<p className="rounded-2xl bg-content1 p-8 text-center text-sm text-default-500">Потоков пока нет</p>}
          query={courses}
          skeleton={<div className="grid gap-4 lg:grid-cols-2">{chartSkeleton}{chartSkeleton}</div>}
        >
          {(data) => <CoursesTab items={data.items} />}
        </QueryState>
      )}
    </>
  );
}
