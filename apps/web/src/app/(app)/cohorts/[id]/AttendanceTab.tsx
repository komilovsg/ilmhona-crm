"use client";

import { useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { ListSkeleton } from "@/components/Skeletons";
import { LoadingButton } from "@/components/LoadingButton";
import { Segmented } from "@/components/Segmented";
import { PersonStatus } from "@/components/StatusChip";
import { useRefreshAttendance } from "@/hooks/attendance";
import { api } from "@/lib/api";
import { lessonProgress, markedLabel, markState, percentLabel } from "@/lib/attendance";
import {
  ALL_MONTHS,
  cellMarkable,
  defaultMonth,
  lessonsOfMonth,
  markLabel,
  monthLabel,
  monthsOf,
  nextPresent,
  withMark,
  type Mark,
} from "@/lib/attendance-grid";
import { useBrowserValue } from "@/lib/client-store";
import { dayMonth, dayTitle, fullDate, todayIso } from "@/lib/education";
import { notify, notifyError } from "@/lib/toast";
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

type Col = AttendanceGrid["lessons"][number];

const CELL = "mx-auto flex h-7 w-7 items-center justify-center rounded-md text-sm font-semibold";

/** A cell of the journal in «Отметка» mode: same box as `Cell`, but a button. */
function MarkCell({
  student,
  lesson,
  busy,
  onToggle,
}: {
  student: GridStudent;
  lesson: Col;
  busy: boolean;
  onToggle: () => void;
}) {
  const mark = student.marks[lesson.id];

  return (
    <button
      aria-busy={busy}
      aria-label={`${student.student_name}, ${fullDate(lesson.date)}: ${markLabel(mark?.present)}`}
      className={clsx(
        CELL,
        "transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
        busy && "opacity-60",
        mark?.present === true && "bg-success/15 text-success-700 dark:text-success",
        mark?.present === false && "bg-danger/15 text-danger",
        mark === undefined && "border border-dashed border-default-400 text-default-400 hover:bg-default-100",
      )}
      title={mark?.present === false ? (mark.reason ?? undefined) : undefined}
      type="button"
      onClick={onToggle}
    >
      {mark?.present === true && <Icon name="check" size={16} strokeWidth={2.6} />}
      {mark?.present === false && <Icon name="x" size={16} strokeWidth={2.6} />}
      {mark === undefined && "·"}
    </button>
  );
}

type View = "view" | "mark";
const VIEW_KEY = "attendance-view";

const VIEW_EVENT = "attendance-view";

function readView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "mark" ? "mark" : "view";
  } catch {
    return "view"; // storage blocked: the page works without it
  }
}

function useViewMode(): [View, (v: View) => void] {
  const view = useBrowserValue<View>(readView, "view", VIEW_EVENT);

  return [
    view,
    (v) => {
      try {
        localStorage.setItem(VIEW_KEY, v);
      } catch {
        /* ignore */
      }
      window.dispatchEvent(new Event(VIEW_EVENT));
    },
  ];
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
  const queryClient = useQueryClient();
  const refresh = useRefreshAttendance();
  const [storedView, setView] = useViewMode();
  const [picked, setPicked] = useState<string | null>(null);
  const months = monthsOf(grid.lessons);
  const month = picked && (picked === ALL_MONTHS || months.includes(picked)) ? picked : defaultMonth(grid.lessons, today);
  const { students } = grid;
  const lessons = lessonsOfMonth(grid.lessons, month);
  const marking = canMark && storedView === "mark";
  const inflight = useRef(new Set<string>());
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<string | null>(null);
  const gridKey = ["grid", cohortId];

  const settle = () => {
    // refetch once nothing is in flight, so a refetch never overwrites a pending optimistic cell
    if (inflight.current.size > 0) return;
    void refresh();
    void queryClient.invalidateQueries({ queryKey: ["lesson-attendance"] });
  };

  const patch = (enrollmentId: string, lessonId: string, mark: Mark | undefined) =>
    queryClient.setQueryData<AttendanceGrid>(gridKey, (old) =>
      old
        ? {
            ...old,
            students: old.students.map((s) =>
              s.enrollment_id === enrollmentId ? { ...s, marks: withMark(s.marks, lessonId, mark) } : s,
            ),
          }
        : old,
    );

  const toggle = async (student: GridStudent, lesson: Col) => {
    const key = `${lesson.id}:${student.enrollment_id}`;

    if (inflight.current.has(key)) return;
    inflight.current.add(key);
    setPending(new Set(inflight.current));
    const prev = student.marks[lesson.id];
    const present = nextPresent(prev?.present);

    await queryClient.cancelQueries({ queryKey: gridKey });
    patch(student.enrollment_id, lesson.id, { present, reason: null });
    try {
      await api(`/api/v1/lessons/${lesson.id}/attendance/${student.enrollment_id}`, {
        method: "PUT",
        body: { present, reason: null },
      });
    } catch (e) {
      patch(student.enrollment_id, lesson.id, prev);
      notifyError(e);
    } finally {
      inflight.current.delete(key);
      setPending(new Set(inflight.current));
      settle();
    }
  };

  const allPresent = async (lesson: Col) => {
    if (bulk) return;
    setBulk(lesson.id);
    try {
      await api(`/api/v1/lessons/${lesson.id}/attendance/all-present`, { method: "POST" });
      notify("Все отмечены присутствующими");
    } catch (e) {
      notifyError(e);
    } finally {
      setBulk(null);
      settle();
    }
  };

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

      <div className="mb-3 hidden flex-wrap items-center gap-3 md:flex">
        <Segmented
          label="Месяц"
          options={[...months.map((m) => ({ key: m, label: monthLabel(m) })), { key: ALL_MONTHS, label: "Все" }]}
          value={month}
          onChange={setPicked}
        />
        {canMark && (
          <Segmented
            label="Режим таблицы"
            options={[
              { key: "view", label: "Просмотр" },
              { key: "mark", label: "Отметка" },
            ]}
            value={storedView}
            onChange={setView}
          />
        )}
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
                    "min-w-14 border-b border-divider px-1 py-2 text-center text-xs tabular-nums",
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
                  <div className="mt-1 flex h-6 items-center justify-center">
                    {marking && l.writable && (
                      <LoadingButton
                        aria-label={`Все присутствовали ${dayTitle(l.date)}`}
                        className="h-6 min-w-0 px-1.5 text-xs"
                        isLoading={bulk === l.id}
                        size="sm"
                        variant="flat"
                        onPress={() => void allPresent(l)}
                      >
                        Все ✓
                      </LoadingButton>
                    )}
                  </div>
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
                    {marking && cellMarkable(l, s) ? (
                      <MarkCell
                        busy={pending.has(`${l.id}:${s.enrollment_id}`)}
                        lesson={l}
                        student={s}
                        onToggle={() => void toggle(s, l)}
                      />
                    ) : (
                      <Cell lesson={l} student={s} />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* phone: the list of lessons; a tap opens the mark screen (one lesson per screen, #23) */}
      <ul data-rows className="space-y-2 md:hidden">
        {grid.lessons.map((l) => {
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
