"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { Icon } from "../Icon";
import { QueryState } from "../QueryState";
import { Bone } from "../Skeletons";

import { dayTitle } from "@/lib/education";
import { lessonsWord, markedLabel, markState } from "@/lib/attendance";
import { dushanbeMinutes, inDays, lessonPhases, splitUnfilled, type LessonPhase } from "@/lib/today";
import type { LessonItem, TodayData } from "@/lib/types";
import { useToday } from "@/hooks/attendance";

/** Minutes of the Dushanbe clock, refreshed every 30 s so «сейчас» moves on its own. */
function useDushanbeMinutes(): number {
  const [min, setMin] = useState(() => dushanbeMinutes(new Date()));

  useEffect(() => {
    const id = setInterval(() => setMin(dushanbeMinutes(new Date())), 30_000);

    return () => clearInterval(id);
  }, []);

  return min;
}

function studentsWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} студент`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} студента`;

  return `${n} студентов`;
}

const PHASE_LABEL: Partial<Record<LessonPhase, string>> = { now: "Идёт сейчас", next: "Дальше" };

function LessonCard({ lesson, phase }: { lesson: LessonItem; phase: LessonPhase }) {
  const state = markState(lesson.marked, lesson.total);
  const focal = phase === "now" || phase === "next";
  const label = PHASE_LABEL[phase];

  return (
    <li className="relative grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-3 sm:grid-cols-[4rem_minmax(0,1fr)] sm:gap-x-4">
      {/* time column + rail: the dot marks the lesson, the line runs to the next one */}
      <div className="flex flex-col items-end pt-4 text-right tabular-nums">
        <span className={clsx("leading-none", focal ? "text-xl font-semibold" : "text-base font-medium text-default-700")}>
          {lesson.start}
        </span>
        <span className="mt-1 text-xs text-default-500">{lesson.end}</span>
      </div>
      <div className="relative pb-3 pl-5">
        <span aria-hidden="true" className="absolute -bottom-0 left-[3px] top-0 w-px bg-default-200" />
        <span
          aria-hidden="true"
          className={clsx(
            "absolute left-0 top-[1.15rem] size-[7px] rounded-full",
            focal ? "bg-primary ring-4 ring-primary/20" : phase === "past" ? "bg-default-300" : "bg-default-400",
          )}
        />
        <div
          className={clsx(
            "rounded-2xl bg-content1 shadow-sm",
            focal ? "p-4 ring-2 ring-primary/50 sm:p-5" : "p-4",
            phase === "past" && state === "done" && "opacity-75",
          )}
          data-tour={focal ? "focus" : undefined}
        >
          {label && (
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-text">
              {phase === "now" && (
                <span aria-hidden="true" className="relative flex size-2">
                  <span className="absolute inline-flex size-full rounded-full bg-primary opacity-60 motion-safe:animate-ping" />
                  <span className="relative inline-flex size-2 rounded-full bg-primary" />
                </span>
              )}
              {label}
            </div>
          )}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <div className="min-w-0">
              <div className={clsx("font-semibold sm:truncate", focal ? "text-lg" : "text-base")}>{lesson.course_name}</div>
              <div className="mt-0.5 text-sm text-default-600">
                {lesson.cohort_code} · {lesson.room_name} · {studentsWord(lesson.total)}
              </div>
            </div>
            <span
              className={clsx(
                "w-fit shrink-0 rounded-full px-2.5 py-1 text-xs font-medium",
                state === "done" && "bg-success/15 text-success-700 dark:text-success",
                state === "partial" && "bg-warning/20 text-warning-700 dark:text-warning",
                state === "none" && "bg-default-100 text-default-600",
              )}
            >
              {markedLabel(lesson.marked, lesson.total)}
            </span>
          </div>
          <Button
            as={Link}
            className="mt-3 h-12 w-full px-3 text-base font-medium"
            color="primary"
            data-tour={focal ? "mark" : undefined}
            href={`/lessons/${lesson.lesson_id}`}
            radius="lg"
            startContent={<Icon className="shrink-0" name="attendance" size={20} />}
            variant={focal ? "solid" : "flat"}
          >
            Отметить посещаемость
          </Button>
        </div>
      </div>
    </li>
  );
}

function Schedule({ data }: { data: TodayData }) {
  const nowMin = useDushanbeMinutes();
  const lessons = data.today;
  const phases = lessonPhases(lessons, nowMin);

  if (lessons.length === 0) {
    const next = data.next_lesson;

    return (
      <section aria-label="Расписание" className="rounded-2xl bg-content1 p-6 text-center shadow-sm sm:p-8" data-tour="timeline">
        <span className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-primary/10 text-brand-text">
          <Icon name="calendar" size={22} />
        </span>
        <p className="text-lg font-semibold">Сегодня уроков нет</p>
        {next ? (
          <>
            <p className="mt-1 text-sm text-default-600">
              Следующий урок — {dayTitle(next.date)}, {next.start} ({inDays(data.date, next.date)})
            </p>
            <p className="mt-0.5 text-sm text-default-500">
              {next.course_name} · {next.cohort_code} · {next.room_name}
            </p>
          </>
        ) : (
          <p className="mt-1 text-sm text-default-500">Ближайших уроков в расписании нет.</p>
        )}
      </section>
    );
  }

  return (
    <section aria-label="Расписание" data-tour="timeline">
      <ol>
        {lessons.map((l, i) => (
          <LessonCard key={l.lesson_id} lesson={l} phase={phases[i]} />
        ))}
      </ol>
    </section>
  );
}

function UnfilledRow({ item }: { item: LessonItem }) {
  return (
    <li>
      <Link
        className="flex min-h-14 items-center justify-between gap-3 rounded-xl px-3 py-2 transition-colors hover:bg-default-100"
        href={`/lessons/${item.lesson_id}`}
      >
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {dayTitle(item.date)} · {item.start}
          </div>
          <div className="truncate text-xs text-default-500">
            {item.cohort_code} · {item.course_name} · {markedLabel(item.marked, item.total)}
          </div>
        </div>
        <Icon className="shrink-0 text-default-400" name="chevron-right" size={18} />
      </Link>
    </li>
  );
}

function Undone({ data }: { data: TodayData }) {
  const { week, earlier } = splitUnfilled(data.unfilled, data.date);
  const total = data.unfilled.length;

  return (
    <section aria-labelledby="undone-title" className="rounded-2xl bg-content1 p-4 shadow-sm" data-tour="undone">
      <div className="mb-1 flex items-center justify-between gap-3 px-1">
        <h2 className="text-lg font-semibold" id="undone-title">
          Не отмечено
        </h2>
        {total > 0 && (
          <span className="rounded-full bg-secondary/15 px-2.5 py-0.5 text-xs font-medium text-secondary">
            {lessonsWord(total)}
          </span>
        )}
      </div>
      {total === 0 ? (
        <p className="flex items-center gap-2 px-1 py-3 text-sm text-default-600">
          <Icon className="text-success" name="check" size={18} />
          Все прошедшие уроки отмечены.
        </p>
      ) : (
        <>
          {week.length > 0 && (
            <>
              <p className="mt-2 px-1 text-xs font-medium uppercase tracking-wide text-default-500">На этой неделе</p>
              <ul>
                {week.map((l) => (
                  <UnfilledRow key={l.lesson_id} item={l} />
                ))}
              </ul>
            </>
          )}
          {earlier.length > 0 && (
            <>
              <p className="mt-2 px-1 text-xs font-medium uppercase tracking-wide text-default-500">Раньше</p>
              <ul>
                {earlier.map((l) => (
                  <UnfilledRow key={l.lesson_id} item={l} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

/** Skeleton with the same grid, rail and card heights as the loaded screen (CLS ~0). */
export function InstructorTodaySkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div>
        {[0, 1].map((i) => (
          <div key={i} className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-3 sm:grid-cols-[4rem_minmax(0,1fr)] sm:gap-x-4">
            <div className="flex flex-col items-end pt-4">
              <Bone className="h-5 w-10" />
              <Bone className="mt-1 h-3 w-8" />
            </div>
            <div className="pb-3 pl-5">
              <Bone className={clsx("w-full rounded-2xl", i === 0 ? "h-[10.5rem]" : "h-[9.5rem]")} />
            </div>
          </div>
        ))}
      </div>
      <div>
        <Bone className="h-64 w-full rounded-2xl" />
      </div>
    </div>
  );
}

export function InstructorToday() {
  const today = useToday();
  const data = today.data;
  const n = data?.today.length ?? 0;
  const students = data?.today.reduce((s, l) => s + l.total, 0) ?? 0;

  return (
    <>
      <p className="-mt-3 mb-5 min-h-5 text-sm text-default-500">
        {data ? dayTitle(data.date) : ""}
        {n > 0 ? ` · ${lessonsWord(n)}, ${studentsWord(students)}` : ""}
      </p>
    <QueryState errorText="Не удалось загрузить уроки" query={today} skeleton={<InstructorTodaySkeleton />}>
      {(data) => (
        <>
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Schedule data={data} />
            <Undone data={data} />
          </div>
        </>
      )}
    </QueryState>
    </>
  );
}
