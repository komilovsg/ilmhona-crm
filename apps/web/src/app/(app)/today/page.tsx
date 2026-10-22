"use client";

import Link from "next/link";
import clsx from "clsx";

import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { UnfilledPanel } from "@/components/UnfilledPanel";
import { ExportButton } from "@/components/ExportButton";
import { useToday } from "@/hooks/attendance";
import { markedLabel, markState } from "@/lib/attendance";
import { dayTitle } from "@/lib/education";

export default function TodayPage() {
  const today = useToday();

  return (
    <>
      <PageHeader actions={<ExportButton path="/api/v1/me/today/export" />} title="Сегодня" />
      <p className="-mt-3 mb-5 text-sm text-default-500">{today.data ? dayTitle(today.data.date) : " "}</p>

      <QueryState
        errorText="Не удалось загрузить уроки"
        query={today}
        skeleton={
          <div className="mb-6 grid gap-3 md:grid-cols-2">
            {[0, 1].map((i) => (
              <Bone key={i} className="h-28 w-full rounded-2xl" />
            ))}
          </div>
        }
      >
        {(data) =>
          data.today.length === 0 ? (
            <div className="mb-6">
              <EmptyState title="Сегодня уроков нет" />
            </div>
          ) : (
            <ul className="mb-6 grid gap-3 md:grid-cols-2">
              {data.today.map((l) => {
                const state = markState(l.marked, l.total);

                return (
                  <li key={l.lesson_id}>
                    <Link
                      className="flex min-h-28 items-center justify-between gap-3 rounded-2xl bg-content1 p-5 shadow-sm transition-colors hover:bg-default-100"
                      href={`/lessons/${l.lesson_id}`}
                    >
                      <div className="min-w-0">
                        <div className="truncate text-lg font-semibold">{l.course_name}</div>
                        <div className="mt-1 text-sm tabular-nums text-default-600">
                          {l.start}–{l.end} · {l.room_name}
                        </div>
                        <div className="mt-0.5 text-xs text-default-500">
                          {l.cohort_code}
                          {l.instructor_name ? ` · ${l.instructor_name}` : ""}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-2">
                        <span
                          className={clsx(
                            "rounded-full px-3 py-1 text-sm font-medium",
                            state === "done" && "bg-success/15 text-success-700 dark:text-success",
                            state === "partial" && "bg-warning/20 text-warning-700 dark:text-warning",
                            state === "none" && "bg-secondary/15 text-secondary",
                          )}
                        >
                          {markedLabel(l.marked, l.total)}
                        </span>
                        <Icon className="text-default-400" name="chevron-right" size={20} />
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )
        }
      </QueryState>

      <UnfilledPanel />
    </>
  );
}
