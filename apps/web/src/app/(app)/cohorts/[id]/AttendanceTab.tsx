"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { PersonStatus } from "@/components/StatusChip";
import { api } from "@/lib/api";
import { lessonProgress, markedLabel, markState, percentLabel } from "@/lib/attendance";
import { dayMonth, dayTitle, todayIso } from "@/lib/education";
import type { AttendanceGrid, GridStudent } from "@/lib/types";

const ImportJournal = dynamic(() => import("./ImportJournal").then((m) => m.ImportJournal));

function ImportButton({ onPress }: { onPress: () => void }) {
  return (
    <Button startContent={<Icon name="upload" size={18} />} variant="flat" onPress={onPress}>
      Импорт из Excel
    </Button>
  );
}

function Cell({ student, lesson }: { student: GridStudent; lesson: AttendanceGrid["lessons"][number] }) {
  const mark = student.marks[lesson.id];
  const base = "mx-auto flex h-7 w-7 items-center justify-center rounded-md text-sm font-semibold";

  if (mark?.present === true)
    return (
      <span aria-label="присутствовал" className={clsx(base, "bg-success/15 text-success-700 dark:text-success")} role="img">
        <Icon name="check" size={16} strokeWidth={2.6} />
      </span>
    );
  if (mark?.present === false)
    return (
      <span
        aria-label={mark.reason ? `отсутствовал: ${mark.reason}` : "отсутствовал"}
        className={clsx(base, "bg-danger/15 text-danger")}
        role="img"
        title={mark.reason ?? undefined}
      >
        <Icon name="x" size={16} strokeWidth={2.6} />
      </span>
    );
  if (lesson.cancelled) return <span className={clsx(base, "text-default-300")}>—</span>;
  if (lesson.held)
    return (
      <span aria-label="не отмечено" className={clsx(base, "border border-dashed border-secondary/60 text-secondary")} role="img">
        ?
      </span>
    );

  return <span className={clsx(base, "text-default-300")}>·</span>;
}

function Unmarked({ n }: { n: number }) {
  return n > 0 ? (
    <span className="whitespace-nowrap rounded-full bg-secondary/15 px-2 py-0.5 text-xs font-medium text-secondary">не отмечено: {n}</span>
  ) : (
    <span className="whitespace-nowrap text-xs text-default-400">всё отмечено</span>
  );
}

export function AttendanceTab({ cohortId, canMark }: { cohortId: string; canMark: boolean }) {
  const grid = useQuery({
    queryKey: ["grid", cohortId],
    queryFn: () => api<AttendanceGrid>(`/api/v1/cohorts/${cohortId}/attendance`),
  });
  const today = todayIso();
  const [importing, setImporting] = useState(false);
  const onImport = canMark ? () => setImporting(true) : undefined;

  return (
    <>
      <QueryState
        empty={
          <EmptyState
            action={onImport && <ImportButton onPress={onImport} />}
            hint="В потоке нет студентов или уроков."
            title="Нечего отмечать"
          />
        }
        errorText="Не удалось загрузить посещаемость"
        isEmpty={(g) => g.students.length === 0 || g.lessons.length === 0}
        query={grid}
        skeleton={<ListSkeleton cols={8} rows={6} />}
      >
        {(data) => <Grid canMark={canMark} cohortId={cohortId} grid={data} today={today} onImport={onImport} />}
      </QueryState>
      {importing && <ImportJournal cohortId={cohortId} onClose={() => setImporting(false)} />}
    </>
  );
}

function Grid({
  grid,
  cohortId,
  canMark,
  today,
  onImport,
}: {
  grid: AttendanceGrid;
  cohortId: string;
  canMark: boolean;
  today: string;
  onImport?: () => void;
}) {
  const { lessons, students } = grid;
  const progress = lessonProgress(grid, (iso) => todayIso(new Date(iso)));
  const header = (l: AttendanceGrid["lessons"][number]) => (
    <>
      <span className="block font-medium">{dayMonth(l.date)}</span>
      <span className="block font-normal text-default-400">{l.start}</span>
    </>
  );

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-default-500">
          <b className="text-default-700">%</b> считается от проведённых уроков, пока студент в потоке; неотмеченные
          уроки показаны отдельно.
        </p>
        <div className="flex flex-wrap gap-2">
          {onImport && <ImportButton onPress={onImport} />}
          <ExportButton label="Табель" path={`/api/v1/cohorts/${cohortId}/attendance/export`} />
        </div>
      </div>

      <div className="hidden overflow-x-auto rounded-2xl bg-content1 md:block">
        <table className="w-full border-separate border-spacing-0 text-left text-sm">
          <thead className="text-xs text-default-500">
            <tr>
              <th className="sticky left-0 z-10 min-w-48 border-b border-divider bg-content1 px-4 py-3 font-medium">Студент</th>
              <th className="min-w-28 whitespace-nowrap border-b border-divider px-3 py-3 text-right font-medium">Посещ.</th>
              <th className="min-w-40 whitespace-nowrap border-b border-divider px-3 py-3 font-medium">Не отмечено</th>
              {lessons.map((l) => (
                <th
                  key={l.id}
                  className={clsx(
                    "border-b border-divider px-1 py-2 text-center text-xs tabular-nums",
                    l.date === today && "bg-primary/10",
                    l.cancelled && "line-through opacity-60",
                  )}
                >
                  {canMark && !l.cancelled && l.date <= today ? (
                    <Link
                      aria-label={`Отметить урок ${dayTitle(l.date)}`}
                      className="block rounded-md px-1.5 py-0.5 hover:bg-default-100"
                      href={`/lessons/${l.id}`}
                    >
                      {header(l)}
                    </Link>
                  ) : (
                    header(l)
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {students.map((s) => (
              <tr key={s.enrollment_id} className="group">
                <th
                  className="sticky left-0 z-10 border-b border-divider bg-content1 px-4 py-2 font-medium group-hover:bg-default-50"
                  scope="row"
                >
                  <div className="truncate">{s.student_name}</div>
                  {s.status !== "активный" && <PersonStatus status={s.status} />}
                </th>
                <td className="min-w-28 whitespace-nowrap border-b border-divider px-3 py-2 text-right tabular-nums">
                  <div className="font-medium">{percentLabel(s.percent)}</div>
                  <div className="text-xs text-default-500">
                    {s.present} из {s.held}
                  </div>
                </td>
                <td className="min-w-40 whitespace-nowrap border-b border-divider px-3 py-2">
                  <Unmarked n={s.unmarked} />
                </td>
                {lessons.map((l) => (
                  <td key={l.id} className={clsx("border-b border-divider px-1 py-2", l.date === today && "bg-primary/5")}>
                    <Cell lesson={l} student={s} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* phone: the list of lessons; a tap opens the mark screen (one lesson per screen, #23) */}
      <ul data-rows className="space-y-2 md:hidden">
        {lessons.map((l) => {
          const p = progress[l.id] ?? { marked: 0, total: 0 };
          const state = markState(p.marked, p.total);
          const inner = (
            <>
              <div className="min-w-0">
                <div className={clsx("font-medium", l.cancelled && "line-through")}>
                  {dayTitle(l.date)}.{l.date.slice(0, 4)}
                  {l.date === today && <span className="ml-2 text-xs text-brand-text">сегодня</span>}
                </div>
                <div className="text-sm tabular-nums text-default-600">
                  {l.start}–{l.end}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={clsx(
                    "rounded-full px-2.5 py-1 text-xs font-medium",
                    l.cancelled && "bg-danger/10 text-danger",
                    !l.cancelled && state === "done" && "bg-success/15 text-success-700 dark:text-success",
                    !l.cancelled && state === "partial" && "bg-warning/20 text-warning-700 dark:text-warning",
                    !l.cancelled && state === "none" && (l.held ? "bg-secondary/15 text-secondary" : "bg-default-100 text-default-500"),
                  )}
                >
                  {l.cancelled ? "отменён" : l.date > today ? "ещё впереди" : !l.held && p.marked === 0 ? "ещё не был" : markedLabel(p.marked, p.total)}
                </span>
                {canMark && !l.cancelled && l.date <= today && <Icon className="text-default-400" name="chevron-right" size={18} />}
              </div>
            </>
          );

          return (
            <li key={l.id}>
              {canMark && !l.cancelled && l.date <= today ? (
                <Link className="flex min-h-16 items-center justify-between gap-2 rounded-2xl bg-content1 p-4" href={`/lessons/${l.id}`}>
                  {inner}
                </Link>
              ) : (
                <div className={clsx("flex min-h-16 items-center justify-between gap-2 rounded-2xl bg-content1 p-4", l.cancelled && "opacity-70")}>
                  {inner}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
