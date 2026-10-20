"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { SelectField } from "@/components/SelectField";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { addDays, dayMonth, dayTitle, mondayOf, todayIso, weekOf } from "@/lib/education";
import { useIsPhone } from "@/lib/client-store";
import type { GridLesson, Room, ScheduleGrid } from "@/lib/types";

function Block({ lesson }: { lesson: GridLesson }) {
  return (
    <Link
      className="block rounded-lg border-l-2 border-primary bg-primary/10 px-2 py-1 text-xs hover:bg-primary/20"
      href={`/cohorts/${lesson.cohort_id}`}
      title={[lesson.course_name, lesson.instructor_name].filter(Boolean).join(" · ")}
    >
      <div className="font-semibold tabular-nums">
        {lesson.start}–{lesson.end}
      </div>
      <div className="truncate">
        {lesson.cohort_code} · {lesson.course_name}
      </div>
    </Link>
  );
}

function DesktopGrid({ grid, days, today }: { grid: ScheduleGrid; days: string[]; today: string }) {
  const lessonsOf = (room: Room, day: string) =>
    grid.lessons.filter((l) => l.room_id === room.id && l.date === day);

  return (
    <div className="overflow-x-auto rounded-2xl bg-content1">
      <table className="w-full min-w-[900px] table-fixed text-left text-sm">
        <thead className="border-b border-divider text-xs text-default-500">
          <tr>
            <th className="w-36 px-3 py-3 font-medium">Аудитория</th>
            {days.map((d) => (
              <th
                key={d}
                className={clsx("px-2 py-3 font-medium", d === today && "text-brand-text")}
                scope="col"
              >
                {dayTitle(d)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.rooms.map((room) => (
            <tr key={room.id} className="border-b border-divider align-top last:border-0">
              <th className="px-3 py-3 text-left font-medium" scope="row">
                {room.name}
                <div className="text-xs font-normal text-default-500">{room.branch_name}</div>
              </th>
              {days.map((d) => (
                <td key={d} className={clsx("space-y-1 px-1.5 py-2", d === today && "bg-primary/5")}>
                  {lessonsOf(room, d).map((l) => (
                    <Block key={l.id} lesson={l} />
                  ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PhoneDay({ grid, day }: { grid: ScheduleGrid; day: string }) {
  return (
    <ul className="space-y-3">
      {grid.rooms.map((room) => {
        const lessons = grid.lessons.filter((l) => l.room_id === room.id && l.date === day);

        return (
          <li key={room.id} className="rounded-2xl bg-content1 p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="font-medium">{room.name}</span>
              <span className="text-xs text-default-500">{room.branch_name}</span>
            </div>
            {lessons.length === 0 ? (
              <p className="text-sm text-default-500">Свободна</p>
            ) : (
              <div className="space-y-1.5">
                {lessons.map((l) => (
                  <Block key={l.id} lesson={l} />
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Week grid (rooms × days) on a desktop; one day with prev / next buttons on a phone. */
export function ScheduleTab() {
  const phone = useIsPhone();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const today = todayIso();
  const [day, setDay] = useState(today);
  const [branch, setBranch] = useState<string | null>(null);
  const monday = mondayOf(day);
  const days = weekOf(day);

  const grid = useQuery({
    queryKey: ["schedule", monday, branch],
    queryFn: () =>
      api<ScheduleGrid>("/api/v1/rooms/schedule", {
        params: { date_from: monday, branch_id: branch ?? undefined },
      }),
    placeholderData: keepPreviousData,
  });

  const step = phone ? 1 : 7;
  const title = phone ? dayTitle(day) : `${dayMonth(days[0])} – ${dayMonth(days[6])}`;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button isIconOnly aria-label="Назад" variant="flat" onPress={() => setDay(addDays(day, -step))}>
          <Icon name="chevron-left" />
        </Button>
        <div className="min-w-32 text-center text-base font-medium">{title}</div>
        <Button isIconOnly aria-label="Вперёд" variant="flat" onPress={() => setDay(addDays(day, step))}>
          <Icon name="chevron-right" />
        </Button>
        <Button variant="flat" onPress={() => setDay(today)}>
          Сегодня
        </Button>
        <ExportButton params={{ date_from: monday, branch_id: branch }} path="/api/v1/rooms/schedule/export" />
        {!me?.branch && (
          <SelectField
            allLabel="Все филиалы"
            className="w-full md:ml-auto md:w-48"
            label="Филиал"
            options={branches.map((b) => ({ key: b.id, label: b.name }))}
            value={branch}
            onChange={setBranch}
          />
        )}
      </div>
      <QueryState
        empty={<EmptyState title="Нет аудиторий" />}
        isEmpty={(d) => d.rooms.length === 0}
        query={grid}
        skeleton={<Bone className="h-96 w-full rounded-2xl" />}
      >
        {(data) => (phone ? <PhoneDay day={day} grid={data} /> : <DesktopGrid days={days} grid={data} today={today} />)}
      </QueryState>
    </>
  );
}
