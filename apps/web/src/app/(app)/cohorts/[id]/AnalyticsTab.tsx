"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Chip } from "@heroui/chip";

import { BarList } from "@/components/charts/BarList";
import { WeekBars } from "@/components/charts/WeekBars";
import { ContactButtons } from "@/components/ContactButtons";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Icon } from "@/components/Icon";
import { ExportButton } from "@/components/ExportButton";
import { Segmented } from "@/components/Segmented";
import { AnalyticsSkeleton } from "@/components/Skeletons";
import { api } from "@/lib/api";
import {
  leftLine,
  pct,
  periodLabel,
  PERIODS,
  retentionLine,
  statusLabel,
  type CohortAnalytics,
  type FinalRow,
  type Period,
  type RiskRow,
  type Status,
  type TopRow,
} from "@/lib/analytics";

/** A status is never colour alone: the chip always says «в норме» / «ниже цели». */
function StatusChip({ status }: { status: Status }) {
  return (
    <Chip color={status === "ok" ? "success" : status === "below" ? "warning" : "default"} size="sm" variant="flat">
      {statusLabel(status)}
    </Chip>
  );
}

function Card({ title, aside, className, children }: { title: string; aside?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className={`rounded-2xl bg-content1 p-4 ${className ?? ""}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Retention({ data }: { data: CohortAnalytics }) {
  const r = data.retention;
  const left = leftLine(r.left);

  return (
    <Card aside={<StatusChip status={r.status} />} className="min-h-52" title="Удержание">
      <p className="text-xl font-semibold tabular-nums">{retentionLine(r)}</p>
      <p className="mt-1 text-sm text-default-500">Цель {r.target} % · с первого урока потока</p>
      {left && <p className="mt-3 text-sm text-default-600">{left}</p>}
      <p className="mt-3 text-xs text-default-500">
        Ушедшие — отчисленные и те, кто перестал ходить (3 пропуска подряд). Всегда на сегодня, не зависит от периода.
      </p>
    </Card>
  );
}

function Grades({ data }: { data: CohortAnalytics }) {
  const g = data.grades;
  const rate = g.pass_rate;

  return (
    <Card aside={<StatusChip status={rate.status} />} className="min-h-52" title="Оценки">
      <p className="text-xl font-semibold tabular-nums">
        Проходят {rate.passed} из {rate.of} · {pct(rate.percent)}
      </p>
      <p className="mt-1 mb-3 text-sm text-default-500">
        Цель {rate.target} % · проходной {g.pass_score} · средний прогноз {g.average === null ? "—" : String(g.average).replace(".", ",")}
        {g.no_data > 0 && ` · без оценок ${g.no_data}`}
      </p>
      <BarList
        rows={g.buckets.map((b) => ({ key: b.label, label: b.label, value: b.count, text: `${b.count} чел.` }))}
        title="Прогноз итога, баллы"
      />
    </Card>
  );
}

function Attendance({ data }: { data: CohortAnalytics }) {
  const a = data.attendance;

  return (
    <Card aside={<StatusChip status={a.status} />} className="min-h-80" title="Посещаемость">
      <p className="text-xl font-semibold tabular-nums">{pct(a.percent)}</p>
      <p className="mt-1 mb-3 text-sm text-default-500">
        Цель {a.target} % · проведено уроков {a.lessons} · отмечено {a.marked}
      </p>
      {a.weeks.length === 0 ? (
        <p className="py-10 text-center text-sm text-default-500">В этом периоде нет проведённых уроков</p>
      ) : (
        <WeekBars target={a.target} weeks={a.weeks} />
      )}
    </Card>
  );
}

function StudentLink({ cohortId, row }: { cohortId: string; row: { enrollment_id: string; student_name: string } }) {
  return (
    <Link className="font-medium text-brand-text hover:underline" href={`/cohorts/${cohortId}?tab=attendance&student=${row.enrollment_id}`} title="Открыть в посещаемости">
      {row.student_name}
    </Link>
  );
}

function Risk({ rows, cohortId }: { rows: RiskRow[]; cohortId: string }) {
  return (
    <Card aside={<span className="text-xs text-default-500">{rows.length}</span>} className="min-h-56" title="В зоне риска">
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm text-default-500">Сейчас никто не в зоне риска</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((r) => (
            <li key={r.enrollment_id} className="rounded-xl border border-divider p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <StudentLink cohortId={cohortId} row={r} />
                <Chip color={r.level === "red" ? "danger" : "warning"} size="sm" variant="solid">
                  {r.level === "red" ? "срочно" : "внимание"}
                </Chip>
              </div>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {r.reasons.map((x) => (
                  <li key={x.code}>
                    <Chip color={x.code === "stopped" ? "danger" : "warning"} size="sm" variant="flat">
                      {x.text}
                    </Chip>
                  </li>
                ))}
              </ul>
              {r.phone && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <ContactButtons phone={r.phone} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Top({ rows, data, cohortId }: { rows: TopRow[]; data: CohortAnalytics; cohortId: string }) {
  const t = data.thresholds;

  return (
    <Card aside={<span className="text-xs text-default-500">{rows.length}</span>} className="min-h-56" title="Отличники">
      <p className="mb-3 text-xs text-default-500">
        Посещаемость от {t.top_attendance} % и прогноз от {t.top_projected} баллов.
      </p>
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm text-default-500">Пока таких студентов нет</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.enrollment_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-divider p-3 text-sm">
              <StudentLink cohortId={cohortId} row={r} />
              <span className="tabular-nums text-default-600">
                {pct(r.attendance_percent)} · прогноз {r.projected}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PassChip({ row }: { row: FinalRow }) {
  return (
    <span className="flex flex-wrap gap-1">
      <Chip color={row.passed ? "success" : "default"} size="sm" variant="flat">
        {row.passed ? "зачёт" : "не набрал"}
      </Chip>
      {row.excellent && (
        <Chip color="primary" size="sm" variant="flat">
          отличник
        </Chip>
      )}
    </span>
  );
}

function Final({ data, cohortId }: { data: CohortAnalytics; cohortId: string }) {
  const f = data.final;

  if (!f.available) return null;
  if (f.rows.length === 0) return <EmptyState title="В потоке нет студентов для итогов" />;

  return (
    <Card aside={<span className="text-xs text-default-500">проходной {f.pass_score}</span>} title="Итоги курса">
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-divider text-xs text-default-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Студент</th>
              {f.categories.map((c) => (
                <th key={c.key} className="px-3 py-2 text-right font-medium">
                  {c.name} · {c.weight}
                </th>
              ))}
              <th className="px-3 py-2 text-right font-medium">Итого</th>
              <th className="px-3 py-2 font-medium">Результат</th>
            </tr>
          </thead>
          <tbody>
            {f.rows.map((r) => (
              <tr key={r.enrollment_id} className="border-b border-divider last:border-0">
                <td className="py-2 pr-3">
                  <StudentLink cohortId={cohortId} row={r} />
                </td>
                {f.categories.map((c) => (
                  <td key={c.key} className="px-3 py-2 text-right tabular-nums">
                    {r.points[c.key]}
                  </td>
                ))}
                <td className="px-3 py-2 text-right font-semibold tabular-nums">{r.total}</td>
                <td className="px-3 py-2">
                  <PassChip row={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-2 md:hidden">
        {f.rows.map((r) => (
          <li key={r.enrollment_id} className="rounded-xl border border-divider p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <StudentLink cohortId={cohortId} row={r} />
              <span className="text-base font-semibold tabular-nums">{r.total}</span>
            </div>
            <div className="mt-1 text-xs text-default-500">
              {f.categories.map((c) => `${c.name} ${r.points[c.key]}/${c.weight}`).join(" · ")}
            </div>
            <div className="mt-2">
              <PassChip row={r} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function AnalyticsTab({ cohortId }: { cohortId: string }) {
  const [period, setPeriod] = useState<Period>("course");
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ["analytics", cohortId, period, offset],
    queryFn: () => api<CohortAnalytics>(`/api/v1/cohorts/${cohortId}/analytics?period=${period}&offset=${offset}`),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Segmented
            label="Период аналитики"
            options={PERIODS}
            value={period}
            onChange={(p) => {
              setPeriod(p);
              setOffset(0);
            }}
          />
          <div className="mt-2 flex h-9 items-center gap-1 text-sm">
            {period !== "course" && (
              <>
                <button
                  aria-label="Предыдущий период"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-content2 disabled:opacity-40"
                  disabled={!query.data?.nav.prev}
                  type="button"
                  onClick={() => setOffset(offset - 1)}
                >
                  <Icon name="chevron-left" size={16} />
                </button>
                <span aria-live="polite" className="min-w-36 text-center font-medium">
                  {query.data ? periodLabel(period, query.data.window.from, query.data.window.to) : ""}
                </span>
                <button
                  aria-label="Следующий период"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-content2 disabled:opacity-40"
                  disabled={!query.data?.nav.next}
                  type="button"
                  onClick={() => setOffset(offset + 1)}
                >
                  <Icon name="chevron-right" size={16} />
                </button>
              </>
            )}
            <span className="ml-2 text-xs text-default-500">Влияет на посещаемость</span>
          </div>
        </div>
        <ExportButton params={{ period, offset: String(offset) }} path={`/api/v1/cohorts/${cohortId}/analytics/export`} />
      </div>
      <QueryState
        empty={<EmptyState hint="Добавьте студентов во вкладке «Студенты»." title="В потоке пока нет студентов" />}
        errorText="Не удалось загрузить аналитику"
        isEmpty={(d) => d.retention.started === 0 && d.grades.students + d.grades.no_data === 0 && d.risk.length === 0}
        query={query}
        skeleton={<AnalyticsSkeleton />}
      >
        {(data) => (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Retention data={data} />
              <Grades data={data} />
            </div>
            <Attendance data={data} />
            <div className="grid gap-4 md:grid-cols-2">
              <Risk cohortId={cohortId} rows={data.risk} />
              <Top cohortId={cohortId} data={data} rows={data.top} />
            </div>
            <Final cohortId={cohortId} data={data} />
          </div>
        )}
      </QueryState>
    </>
  );
}
