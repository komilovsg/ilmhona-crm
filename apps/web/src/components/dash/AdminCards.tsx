"use client";

import { useState, type ReactNode } from "react";
import clsx from "clsx";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { useCard } from "@/hooks/dash";
import { api } from "@/lib/api";
import {
  dayMonth,
  laneSpan,
  monthName,
  monthShort,
  plural,
  shortDate,
  signed,
  todayAt,
  trendOf,
  type AlertItem,
  type BranchMonths,
  type Demand,
  type MonthHero,
  type Timeline,
} from "@/lib/dash";
import { formatPrice } from "@/lib/education";
import { compact } from "@/lib/reports";
import type { CourseRow } from "@/lib/reports-types";
import { CardSkeleton, DashCard, GrowX, GrowY, Legend, PulseLine, RowLink, TONE_TEXT, ViewToggle } from "./shell";

/** Chart labels in thousands: 1 840 -> «1,8» (the caption says «тыс. TJS»). */
const thousands = (n: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(n / 1000);

const num = (s: string) => formatPrice(s).replace(/\s*TJS$/, "");

// ---- the month in one sentence --------------------------------------------------------------

const MONTH_DATIVE = ["январю", "февралю", "марту", "апрелю", "маю", "июню", "июлю", "августу", "сентябрю", "октябрю", "ноябрю", "декабрю"];

function previousMonth(iso: string): string {
  const m = Number(iso.slice(5, 7));

  return MONTH_DATIVE[(m + 10) % 12];
}

function Delta({ children, tone }: { children: ReactNode; tone: "up" | "down" | "flat" | "new" }) {
  return <b className={clsx("font-semibold", TONE_TEXT[tone])}>{children}</b>;
}

export function MonthHeroCard({ branch }: { branch: string }) {
  const query = useCard<MonthHero>("month", branch);

  return (
    <DashCard hero label="Месяц одной фразой">
      <QueryState
        bare
        query={query}
        skeleton={
          <div className="flex flex-col gap-4.5">
            <Bone className="h-[6.25rem] w-full rounded-xl md:h-[3.0625rem] md:w-3/4" />
            <Bone className="h-3.5 w-full rounded-full" />
            <Bone className="h-[3.75rem] w-full rounded-lg md:h-6" />
          </div>
        }
      >
        {(d) => {
          const pct = Math.min(Math.max(d.collection_pct, 0), 100);
          const income = d.income_change_pct === null ? null : trendOf(d.income_change_pct);

          return (
            <div className="flex flex-col gap-4.5">
              <p className="font-display text-[1.625rem] font-semibold leading-tight tracking-tight md:text-[2.125rem] md:leading-[1.25]">
                {monthName(d.month)}: собрано <span className="text-brand-text">{num(d.collected)}</span> из {formatPrice(d.expected)}
              </p>
              <div
                aria-label={`Собрано ${Math.round(d.collection_pct)} процентов ожидаемого`}
                className="relative h-3.5 overflow-hidden rounded-full bg-default-200"
                role="img"
              >
                <GrowX className="absolute inset-y-0 left-0 rounded-full" delay={0.2} style={{ width: `${pct}%`, background: "var(--chart-fill)" }} />
              </div>
              <p className="flex flex-wrap gap-x-7 gap-y-1.5 text-[0.9375rem] text-default-500">
                <span>
                  <b className="font-semibold text-foreground">{Math.round(d.collection_pct)} %</b> собираемость
                </span>
                {d.debt !== null && (
                  <span>
                    долг <b className="font-semibold text-foreground">{formatPrice(d.debt)}</b>
                  </span>
                )}
                {d.profit !== null && (
                  <span>
                    прибыль <b className="font-semibold text-foreground">{formatPrice(d.profit)}</b>
                  </span>
                )}
                <span>
                  к {previousMonth(d.month)}:{" "}
                  {income && (
                    <>
                      <Delta tone={income.tone}>{income.text.replace(/^[▲▼] /, d.income_change_pct! > 0 ? "+" : "−")} оплат</Delta> ·{" "}
                    </>
                  )}
                  <Delta tone={d.new_students_change > 0 ? "up" : d.new_students_change < 0 ? "down" : "flat"}>
                    {signed(d.new_students_change)} {plural(Math.abs(d.new_students_change), "студент", "студента", "студентов")}
                  </Delta>
                </span>
              </p>
            </div>
          );
        }}
      </QueryState>
    </DashCard>
  );
}

// ---- cohort timeline ------------------------------------------------------------------------

const LANE = "grid grid-cols-[7.25rem_minmax(0,1fr)] md:grid-cols-[11rem_minmax(0,1fr)] items-center";
const PLOT = "left-[7.25rem] md:left-[11rem]";

function seatsText(l: { enrolled: number; capacity: number; over_capacity: unknown }) {
  return l.over_capacity ? `${l.enrolled} / ${l.capacity} · сверх плана` : `${l.enrolled} / ${l.capacity} мест`;
}

function TimelineChart({ d }: { d: Timeline }) {
  const months = [0, 1, 2].map((i) => {
    const first = new Date(Date.UTC(Number(d.window_start.slice(0, 4)), Number(d.window_start.slice(5, 7)) - 1 + i, 1)).toISOString().slice(0, 10);

    return { iso: first, left: todayAt(first, d.window_start, d.window_end) };
  });
  const today = todayAt(d.today, d.window_start, d.window_end);

  return (
    <div className="flex flex-col gap-2.5">
      <div className={LANE}>
        <span />
        <div className="relative h-5 border-b border-divider text-xs text-default-500">
          {months.map((m) => (
            <span key={m.iso} className="absolute top-0" style={{ left: `${m.left}%` }}>
              <span className={m.left ? "pl-1.5" : ""}>{monthName(m.iso)}</span>
            </span>
          ))}
        </div>
      </div>
      <div className="relative flex flex-col gap-2">
        <div aria-hidden="true" className={clsx("pointer-events-none absolute -top-1 bottom-0 right-0", PLOT)}>
          {months.slice(1).map((m) => (
            <span key={m.iso} className="absolute inset-y-0 w-px" style={{ left: `${m.left}%`, background: "var(--chart-grid)" }} />
          ))}
          <PulseLine left={today} />
        </div>
        {d.items.map((l, i) => {
          const span = laneSpan(l.start_date, l.end_date, d.window_start, d.window_end);
          const fill = Math.min(l.fill_pct, 100);

          return (
            <Link
              key={l.id}
              aria-label={`${l.code}, ${l.course_name}: ${seatsText(l)}, ${dayMonth(l.start_date)} — ${dayMonth(l.end_date)}`}
              className={clsx(LANE, "min-h-14 rounded-lg hover:bg-content2")}
              href={`/cohorts/${l.id}`}
            >
              <span className="flex min-w-0 flex-col pr-2">
                <span className="truncate text-sm font-semibold">{l.code}</span>
                <span className="truncate text-xs text-default-500" title={l.course_name}>
                  {l.course_name}
                </span>
                <span className={clsx("truncate text-xs tabular-nums", l.over_capacity ? "font-medium text-warning-600 dark:text-warning" : "text-default-500")}>
                  {seatsText(l)}
                </span>
              </span>
              <span className="relative h-7">
                <span
                  className={clsx("absolute inset-y-0 overflow-hidden rounded-lg border bg-default-100", l.over_capacity ? "border-2 border-dashed" : "border-default-300")}
                  style={{ left: `${span.left}%`, width: `${span.width}%`, borderColor: l.over_capacity ? "var(--chart-accent)" : undefined }}
                >
                  <GrowX className="h-full" delay={0.1 + i * 0.07} style={{ width: `${fill}%`, background: "var(--chart-fill)" }} />
                </span>
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function TimelineTable({ d }: { d: Timeline }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <caption className="sr-only">Потоки: сроки и занятые места</caption>
        <thead className="border-b border-divider text-xs text-default-500">
          <tr>
            {["Поток", "Курс", "Филиал", "Старт", "Конец", "Места"].map((h) => (
              <th key={h} className="py-2 pr-3 font-medium" scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.items.map((l) => (
            <tr key={l.id} className="border-b border-divider last:border-0">
              <td className="py-2 pr-3 font-medium">
                <Link className="text-brand-text" href={`/cohorts/${l.id}`}>
                  {l.code}
                </Link>
              </td>
              <td className="py-2 pr-3">{l.course_name}</td>
              <td className="py-2 pr-3">{l.branch_name}</td>
              <td className="py-2 pr-3 tabular-nums">{shortDate(l.start_date)}</td>
              <td className="py-2 pr-3 tabular-nums">{shortDate(l.end_date)}</td>
              <td className="py-2 tabular-nums">{seatsText(l)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TimelineCard({ branch }: { branch: string }) {
  const query = useCard<Timeline>("timeline", branch);
  const [table, setTable] = useState(false);

  return (
    <DashCard
      aside={<ViewToggle table={table} onChange={setTable} />}
      className="min-h-[24rem]"
      delay={0.08}
      title="Лента наборов"
    >
      <QueryState
        bare
        empty={<EmptyState bare hint="Потоки на наборе и активные появятся здесь." title="Ближайших наборов нет" />}
        isEmpty={(d) => d.items.length === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-14" rows={5} />}
      >
        {(d) => (
          <div className="flex flex-col gap-4">
            <p className="-mt-2 text-xs text-default-500">
              {monthName(d.window_start)} — {monthName(d.window_end).toLowerCase()} · заполненность мест
            </p>
            {table ? <TimelineTable d={d} /> : <TimelineChart d={d} />}
            {!table && (
              <Legend
                items={[
                  { label: "занято мест", color: "var(--chart-fill)" },
                  { label: "свободно", outline: true },
                  { label: "сверх плана — пунктир", color: "var(--chart-accent)" },
                  { label: "сегодня", color: "var(--chart-accent)", line: true },
                ]}
              />
            )}
          </div>
        )}
      </QueryState>
    </DashCard>
  );
}

// ---- attention ------------------------------------------------------------------------------

const SEVERITY = {
  danger: { word: "Срочно", dot: "bg-danger" },
  warning: { word: "Внимание", dot: "bg-warning" },
  info: { word: "К сведению", dot: "bg-primary" },
} as const;

export function AttentionCard({ branch }: { branch: string }) {
  const query = useCard<{ items: AlertItem[] }>("attention", branch);

  return (
    <DashCard className="min-h-[24rem]" delay={0.16} title="Требует внимания">
      <QueryState
        bare
        empty={<EmptyState bare hint="Переплат, пропущенных отметок и ожидающих оплат нет." title="Срочного ничего нет" />}
        isEmpty={(d) => d.items.length === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-[4.25rem]" rows={4} />}
      >
        {(d) => (
          <ul className="flex flex-col gap-3">
            {d.items.map((a) => (
              <li key={a.key}>
                <RowLink href={a.href}>
                  <span className="flex items-start gap-3">
                    <span aria-hidden="true" className={clsx("mt-1.5 size-2.5 shrink-0 rounded-full", SEVERITY[a.severity].dot)} />
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="text-sm font-semibold">
                        <span className="sr-only">{SEVERITY[a.severity].word}: </span>
                        {a.title}
                      </span>
                      <span className="text-[0.8125rem] text-default-500">{a.hint}</span>
                    </span>
                  </span>
                </RowLink>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </DashCard>
  );
}

// ---- demand ---------------------------------------------------------------------------------

export function DemandCard({ branch }: { branch: string }) {
  const query = useCard<Demand>("demand", branch);

  return (
    <DashCard
      aside={<span className="text-[0.8125rem] text-default-500">лиды, 30 дней</span>}
      className="min-h-[22rem]"
      delay={0.1}
      title="Спрос на курсы"
    >
      <QueryState
        bare
        empty={<EmptyState bare hint="За последние 30 дней заявок не было." title="Лидов нет" />}
        isEmpty={(d) => d.items.length === 0 && d.no_course === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-7" rows={6} />}
      >
        {(d) => (
          <div className="flex flex-col gap-3">
            <ul className="flex flex-col gap-2.5">
              {d.items.map((r) => {
                const t = trendOf(r.change_pct);

                return (
                  <li
                    key={r.course_id}
                    className="grid min-h-7 grid-cols-[minmax(0,1fr)_auto_4.5rem] items-center gap-3 text-sm"
                    title={`${r.course_name}: ${r.leads} за 30 дней, ${r.previous} в предыдущие 30`}
                  >
                    <span className="truncate">{r.course_name}</span>
                    <span className="font-semibold tabular-nums">{r.leads}</span>
                    <span className={clsx("text-right text-[0.8125rem] font-semibold tabular-nums", TONE_TEXT[t.tone])}>{t.text}</span>
                  </li>
                );
              })}
            </ul>
            {d.no_course > 0 && (
              <p className="rounded-xl bg-content2 px-3 py-2.5 text-[0.8125rem] text-default-500">
                Без курса («другое»):{" "}
                <Link className="font-semibold text-foreground underline-offset-2 hover:underline" href="/leads">
                  {d.no_course} {plural(d.no_course, "лид", "лида", "лидов")}
                </Link>
                . Кандидат на новый курс.
              </p>
            )}
          </div>
        )}
      </QueryState>
    </DashCard>
  );
}

// ---- branches by month ----------------------------------------------------------------------

const SERIES_COLORS = ["var(--chart-fill)", "var(--chart-accent)", "var(--series-3)", "var(--series-4)"];

function BranchChart({ d }: { d: BranchMonths }) {
  const values = d.series.map((s) => s.values.map(Number));
  const max = Math.max(1, ...values.flat());
  const last = d.months.length - 1;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative">
        <span className="absolute -top-1 left-0 text-[0.6875rem] text-default-500 tabular-nums">{thousands(max)}</span>
        <div className="grid h-52 grid-cols-6 items-end gap-2.5 border-b border-divider pt-4 md:gap-3.5">
          {d.months.map((m, mi) => {
            const tip = `${monthName(m)}: ${d.series.map((s, si) => `${s.name} ${formatPrice(values[si][mi])}`).join(" · ")}`;

            return (
              <div
                key={m}
                aria-label={tip}
                className="group relative flex h-full items-end justify-center gap-1 rounded-t-md outline-offset-2 hover:bg-content2 focus-visible:outline-2"
                role="img"
                tabIndex={0}
                title={tip}
              >
                {d.series.map((s, si) => (
                  <span key={s.branch_id} className="relative flex h-full w-[38%] max-w-[1.375rem] flex-col justify-end">
                    {mi === last && (
                      <span className="mb-0.5 whitespace-nowrap text-center text-[0.6875rem] font-medium tabular-nums">{thousands(values[si][mi])}</span>
                    )}
                    <GrowY
                      className="w-full rounded-t"
                      delay={0.3 + mi * 0.05 + si * 0.03}
                      style={{ height: `${(values[si][mi] / max) * 100}%`, minHeight: values[si][mi] > 0 ? 2 : 0, background: SERIES_COLORS[si % SERIES_COLORS.length] }}
                    />
                  </span>
                ))}
                <span
                  className={clsx(
                    "pointer-events-none absolute bottom-full z-10 mb-1 hidden w-max max-w-[14rem] rounded-lg bg-foreground px-2.5 py-1.5 text-xs text-background shadow-lg group-hover:block group-focus-visible:block",
                    mi === 0 ? "left-0" : mi === last ? "right-0" : "left-1/2 -translate-x-1/2",
                  )}
                >
                  <span className="block font-medium">{monthName(m)}</span>
                  {d.series.map((s, si) => (
                    <span key={s.branch_id} className="block tabular-nums">
                      {s.name}: {formatPrice(values[si][mi])}
                    </span>
                  ))}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="grid grid-cols-6 gap-2.5 text-center text-xs text-default-500 md:gap-3.5">
        {d.months.map((m) => (
          <span key={m}>{monthShort(m)}</span>
        ))}
      </div>
    </div>
  );
}

function BranchTable({ d }: { d: BranchMonths }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[20rem] text-left text-sm">
        <caption className="sr-only">Доход по филиалам и месяцам, TJS</caption>
        <thead className="border-b border-divider text-xs text-default-500">
          <tr>
            <th className="py-2 pr-3 font-medium" scope="col">
              Месяц
            </th>
            {d.series.map((s) => (
              <th key={s.branch_id} className="py-2 pr-3 text-right font-medium" scope="col">
                {s.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.months.map((m, mi) => (
            <tr key={m} className="border-b border-divider last:border-0">
              <th className="py-2 pr-3 font-normal" scope="row">
                {monthName(m)}
              </th>
              {d.series.map((s) => (
                <td key={s.branch_id} className="py-2 pr-3 text-right tabular-nums">
                  {formatPrice(s.values[mi])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BranchMonthsCard({ branch }: { branch: string }) {
  const query = useCard<BranchMonths>("branches", branch);
  const [table, setTable] = useState(false);

  return (
    <DashCard
      aside={
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Legend items={(query.data?.series ?? []).map((s, i) => ({ label: s.name, color: SERIES_COLORS[i % SERIES_COLORS.length] }))} />
          <ViewToggle table={table} onChange={setTable} />
        </div>
      }
      className="min-h-[22rem]"
      delay={0.24}
      title="Филиалы по месяцам"
    >
      <QueryState
        bare
        empty={<EmptyState bare title="Филиалов нет" />}
        isEmpty={(d) => d.series.length === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-64" rows={1} />}
      >
        {(d) => (table ? <BranchTable d={d} /> : <BranchChart d={d} />)}
      </QueryState>
      <p className="-mt-2 text-xs text-default-500">Подтверждённые оплаты, тыс. TJS, по месяцам оплаты</p>
    </DashCard>
  );
}

// ---- income per course ----------------------------------------------------------------------

const TOP = 6;

export function CoursesIncomeCard({ branch }: { branch: string }) {
  const branch_id = branch === "all" ? undefined : branch;
  const query = useQuery({
    queryKey: ["dashboard", "card", "courses_income", branch_id ?? "all"],
    queryFn: () => api<{ items: CourseRow[] }>("/api/v1/dashboard/by-course", { params: { branch_id } }),
  });
  const [all, setAll] = useState(false);
  const [table, setTable] = useState(false);

  return (
    <DashCard
      aside={
        <div className="flex items-center gap-3">
          <span className="text-[0.8125rem] text-default-500">{all ? "все курсы" : `топ-${TOP}`}</span>
          <ViewToggle table={table} onChange={setTable} />
        </div>
      }
      className="min-h-[22rem]"
      delay={0.32}
      title="Доход по курсам"
    >
      <QueryState
        bare
        empty={<EmptyState bare title="Потоков пока нет" />}
        isEmpty={(d) => d.items.length === 0}
        query={query}
        skeleton={<CardSkeleton rowClass="h-10" rows={TOP} />}
      >
        {(d) => {
          const items = [...d.items].sort((a, b) => Number(b.income) - Number(a.income) || a.course_name.localeCompare(b.course_name, "ru"));
          const shown = all ? items : items.slice(0, TOP);
          const max = Math.max(1, ...items.map((c) => Number(c.income)));
          const rest = items.length - TOP;

          return (
            <div className="flex flex-col gap-3">
              {table ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[18rem] text-left text-sm">
                    <caption className="sr-only">Доход по курсам, TJS</caption>
                    <thead className="border-b border-divider text-xs text-default-500">
                      <tr>
                        <th className="py-2 pr-3 font-medium" scope="col">Курс</th>
                        <th className="py-2 pr-3 text-right font-medium" scope="col">Доход</th>
                        <th className="py-2 text-right font-medium" scope="col">Выпускников</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((c) => (
                        <tr key={c.course_id} className="border-b border-divider last:border-0">
                          <td className="py-2 pr-3">{c.course_name}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{formatPrice(c.income ?? 0)}</td>
                          <td className="py-2 text-right tabular-nums">{c.graduates}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <ul className="flex flex-col gap-3">
                  {shown.map((c, i) => (
                    <li
                      key={c.course_id}
                      className="grid min-h-10 grid-cols-[minmax(0,6.5rem)_minmax(0,1fr)_auto] items-center gap-x-3 md:grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_auto]"
                      title={`${c.course_name}: ${formatPrice(c.income ?? 0)}, выпускников ${c.graduates}`}
                    >
                      <span className="truncate text-sm">{c.course_name}</span>
                      <span className="h-2.5 rounded-full bg-default-100">
                        <GrowX className="h-2.5 rounded-full" delay={0.4 + i * 0.06} style={{ width: `${(Number(c.income) / max) * 100}%`, background: "var(--chart-fill)" }} />
                      </span>
                      <span className="flex min-w-[5.5rem] flex-col items-end leading-tight">
                        <span className="text-sm font-semibold tabular-nums">{compact(Number(c.income))} TJS</span>
                        <span className="text-[0.6875rem] text-default-500">выпускников {c.graduates}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {rest > 0 && (
                <button
                  aria-expanded={all}
                  className="self-start text-sm text-brand-text"
                  type="button"
                  onClick={() => setAll((v) => !v)}
                >
                  {all ? "Свернуть" : `Ещё ${rest} ${plural(rest, "курс", "курса", "курсов")}`}
                </button>
              )}
            </div>
          );
        }}
      </QueryState>
    </DashCard>
  );
}
