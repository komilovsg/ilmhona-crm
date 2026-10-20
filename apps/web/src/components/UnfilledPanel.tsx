"use client";

import Link from "next/link";

import { Icon } from "./Icon";
import { QueryState } from "./QueryState";
import { Bone } from "./Skeletons";

import { useToday } from "@/hooks/attendance";
import { lessonsWord, markedLabel } from "@/lib/attendance";
import { dayTitle } from "@/lib/education";
import type { LessonItem, TodayData } from "@/lib/types";

function Row({ item }: { item: LessonItem }) {
  return (
    <li>
      <Link
        className="flex min-h-14 items-center justify-between gap-3 rounded-xl px-3 py-2 hover:bg-default-100"
        href={`/lessons/${item.lesson_id}`}
      >
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {dayTitle(item.date)} · {item.start} · {item.course_name}
          </div>
          <div className="text-xs text-default-500">
            {item.cohort_code} · {markedLabel(item.marked, item.total)}
          </div>
        </div>
        <Icon className="shrink-0 text-default-400" name="chevron-right" size={18} />
      </Link>
    </li>
  );
}

/**
 * «Не заполнено» (#21): held lessons of the last 30 days with somebody still unmarked. Grouped by
 * instructor when the list holds more than one (the manager's view); the instructor sees their own.
 */
export function UnfilledPanel({ title = "Не заполнено" }: { title?: string }) {
  const today = useToday();

  return (
    <QueryState
      errorText="Не удалось загрузить список"
      query={today}
      skeleton={
        <div className="rounded-2xl bg-content1 p-4">
          <Bone className="mb-3 h-7 w-40" />
          {[0, 1, 2].map((i) => (
            <Bone key={i} className="mb-2 h-14 w-full rounded-xl" />
          ))}
        </div>
      }
    >
      {(data) => <Panel data={data} title={title} />}
    </QueryState>
  );
}

function Panel({ data, title }: { data: TodayData; title: string }) {
  const groups = data.unfilled_by_instructor;
  const count = data.unfilled.length;

  return (
    <section aria-labelledby="unfilled-title" className="rounded-2xl bg-content1 p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold" id="unfilled-title">
          {title}
        </h2>
        {count > 0 && (
          <span className="rounded-full bg-secondary/15 px-2.5 py-0.5 text-xs font-medium text-secondary">
            {lessonsWord(count)}
          </span>
        )}
      </div>
      {count === 0 ? (
        <p className="flex items-center gap-2 py-3 text-sm text-default-600">
          <Icon className="text-success" name="check" size={18} />
          Всё отмечено за последние 30 дней.
        </p>
      ) : (
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.instructor_id ?? "none"}>
              {(groups.length > 1 || g.instructor_name === null) && (
                <h3 className="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-default-500">
                  {g.instructor_name ?? "Без инструктора"} · {lessonsWord(g.lessons.length)}
                </h3>
              )}
              <ul>
                {g.lessons.map((l) => (
                  <Row key={l.lesson_id} item={l} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
