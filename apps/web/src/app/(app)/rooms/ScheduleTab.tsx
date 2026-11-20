"use client";

import { type CSSProperties, useState } from "react";
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
import { SLOT, TICK, boardDays, boardHours, clock, courseHue, linesOf, slotsOf } from "@/lib/schedule-board";
import type { GridLesson, ScheduleGrid } from "@/lib/types";

const LINE_PX = 5; // one TICK of the board: a half-hour row is 30px

function Block({ lesson, style }: { lesson: GridLesson; style: CSSProperties }) {
  const hue = courseHue(lesson.course_name);

  return (
    <Link
      className="z-10 m-px overflow-hidden rounded-md px-1.5 py-0.5 text-center text-[11px] leading-tight text-white hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-1"
      href={`/cohorts/${lesson.cohort_id}`}
      style={{ ...style, backgroundColor: `hsl(${hue} 55% 36%)` }}
      title={[`${lesson.start}–${lesson.end}`, lesson.course_name, lesson.cohort_code, lesson.instructor_name]
        .filter(Boolean)
        .join(" · ")}
    >
      <div className="font-semibold [overflow-wrap:anywhere]">{lesson.course_name}</div>
      <div className="truncate opacity-90">{lesson.cohort_code}</div>
      {lesson.instructor_name && <div className="truncate opacity-90">{lesson.instructor_name}</div>}
    </Link>
  );
}

/** Time down the side, a column per room inside each day; an empty cell is a free room. */
function Board({ grid, days, today }: { grid: ScheduleGrid; days: string[]; today: string }) {
  const rooms = grid.rooms;
  const lessons = grid.lessons.filter((l) => days.includes(l.date));
  const { from, to } = boardHours(lessons);
  const slots = slotsOf(from, to);
  const perSlot = SLOT / TICK;
  const column = (day: number, room: number) => 2 + day * rooms.length + room;
  const HEAD = 2; // the day row and the room row

  return (
    <div className="overflow-x-auto rounded-2xl bg-content1">
      <div
        className="grid text-xs"
        role="table"
        style={{
          gridTemplateColumns: `3.25rem repeat(${days.length * rooms.length}, minmax(5.5rem, 1fr))`,
          gridTemplateRows: `auto auto repeat(${slots.length * perSlot}, ${LINE_PX}px)`,
        }}
      >
        <div className="sticky left-0 z-20 row-span-2 bg-content1" />
        {days.map((d, di) => (
          <div
            key={d}
            className={clsx(
              "border-b border-l-2 border-divider px-2 py-2 text-center text-sm font-medium",
              d === today && "bg-primary/10 text-brand-text",
            )}
            style={{ gridRow: 1, gridColumn: `${column(di, 0)} / span ${rooms.length}` }}
          >
            {dayTitle(d)}
          </div>
        ))}
        {days.map((d, di) =>
          rooms.map((room, ri) => (
            <div
              key={`${d}-${room.id}`}
              className={clsx(
                "truncate border-b border-divider px-1 py-1.5 text-center font-medium text-default-600",
                ri === 0 ? "border-l-2" : "border-l",
              )}
              style={{ gridRow: 2, gridColumn: column(di, ri) }}
              title={`${room.name} · ${room.branch_name}`}
            >
              {room.name}
            </div>
          )),
        )}
        {slots.map((slot, si) => (
          <div
            key={slot}
            className="sticky left-0 z-20 border-b border-divider bg-content1 pr-2 text-right tabular-nums text-default-500"
            style={{ gridColumn: 1, gridRow: `${HEAD + 1 + si * perSlot} / span ${perSlot}` }}
          >
            {clock(slot)}
          </div>
        ))}
        {days.map((d, di) =>
          rooms.map((room, ri) =>
            slots.map((slot, si) => (
              <div
                key={`${d}-${room.id}-${slot}`}
                className={clsx(
                  "border-b border-divider",
                  ri === 0 ? "border-l-2" : "border-l",
                  d === today && "bg-primary/5",
                )}
                style={{ gridColumn: column(di, ri), gridRow: `${HEAD + 1 + si * perSlot} / span ${perSlot}` }}
              />
            )),
          ),
        )}
        {lessons.map((l) => {
          const ri = rooms.findIndex((r) => r.id === l.room_id);

          if (ri < 0) return null;
          const { line, span } = linesOf(l, from);

          return (
            <Block
              key={l.id}
              lesson={l}
              style={{ gridColumn: column(days.indexOf(l.date), ri), gridRow: `${HEAD + line} / span ${span}` }}
            />
          );
        })}
      </div>
    </div>
  );
}

/** The room board: a week on a desktop; one day with prev / next buttons on a phone. */
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
        <Button color="primary" variant="flat" onPress={() => setDay(today)}>
          Сегодня
        </Button>
        <ExportButton params={{ date_from: monday, branch_id: branch }} path="/api/v1/rooms/schedule/export" />
        {!me?.branch && (
          <SelectField filter
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
        {(data) => <Board days={phone ? [day] : boardDays(days, data.lessons)} grid={data} today={today} />}
      </QueryState>
    </>
  );
}
