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
import {
  type MonthSpan,
  type Period,
  PERIODS,
  SLOT,
  TICK,
  boardDays,
  boardHours,
  clock,
  courseHue,
  linesOf,
  monthsOfPeriod,
  periodTitle,
  shiftDay,
  slotsOf,
  weekBands,
} from "@/lib/schedule-board";
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
function Board({
  grid,
  days,
  today,
  hours,
}: {
  grid: ScheduleGrid;
  days: string[];
  today: string;
  hours: { from: number; to: number };
}) {
  const rooms = grid.rooms;
  const lessons = grid.lessons.filter((l) => days.includes(l.date));
  const { from, to } = hours;
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
              "border-b border-l-2 border-divider py-2 text-sm font-medium",
              d === today && "bg-primary/10 text-brand-text",
            )}
            style={{ gridRow: 1, gridColumn: `${column(di, 0)} / span ${rooms.length}` }}
          >
            {/* the day stays in sight while its rooms scroll by */}
            <span className="sticky left-14 inline-block px-2">{dayTitle(d)}</span>
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
        {/* the lines: one strip per half hour across, one per room down */}
        {slots.map((slot, si) => (
          <div
            key={`row-${slot}`}
            className="border-b border-divider"
            style={{ gridColumn: "2 / -1", gridRow: `${HEAD + 1 + si * perSlot} / span ${perSlot}` }}
          />
        ))}
        {days.map((d, di) =>
          rooms.map((room, ri) => (
            <div
              key={`col-${d}-${room.id}`}
              className={clsx("border-divider", ri === 0 ? "border-l-2" : "border-l", d === today && "bg-primary/5")}
              style={{ gridColumn: column(di, ri), gridRow: `${HEAD + 1} / -1` }}
            />
          )),
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

const skeleton = <Bone className="h-96 w-full rounded-2xl" />;
const noRooms = <EmptyState title="Нет аудиторий" />;

/** One month: its weeks one under another, each a board of its own. */
function MonthBoards({ span, branch, today }: { span: MonthSpan; branch: string | null; today: string }) {
  const grid = useQuery({
    queryKey: ["schedule", span.from, span.to, branch],
    queryFn: () =>
      api<ScheduleGrid>("/api/v1/rooms/schedule", {
        params: { date_from: span.from, date_to: span.to, branch_id: branch ?? undefined },
      }),
  });

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-lg font-semibold">{span.title}</h2>
      <QueryState empty={noRooms} isEmpty={(d) => d.rooms.length === 0} query={grid} skeleton={skeleton}>
        {(data) => {
          const hours = boardHours(data.lessons);

          return (
            <div className="space-y-4">
              {weekBands(span.from, span.to).map((week) => (
                // a year is some fifty boards: the ones off screen are not laid out
                <div key={week[0]} style={{ contentVisibility: "auto", containIntrinsicSize: "auto 520px" }}>
                  <Board days={boardDays(week, data.lessons)} grid={data} hours={hours} today={today} />
                </div>
              ))}
            </div>
          );
        }}
      </QueryState>
    </section>
  );
}

/** The room board: a week (one day on a phone), or a month, half a year, a year month by month. */
export function ScheduleTab() {
  const phone = useIsPhone();
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const today = todayIso();
  const [day, setDay] = useState(today);
  const [period, setPeriod] = useState<Period>("week");
  const [branch, setBranch] = useState<string | null>(null);
  const monday = mondayOf(day);
  const days = weekOf(day);
  const weekly = period === "week";

  const grid = useQuery({
    queryKey: ["schedule", monday, branch],
    queryFn: () =>
      api<ScheduleGrid>("/api/v1/rooms/schedule", {
        params: { date_from: monday, branch_id: branch ?? undefined },
      }),
    placeholderData: keepPreviousData,
    enabled: weekly,
  });

  const months = weekly ? [] : monthsOfPeriod(period, day);
  const step = (dir: -1 | 1) => setDay(weekly && phone ? addDays(day, dir) : shiftDay(period, day, dir));
  const title = !weekly
    ? periodTitle(period, day)
    : phone
      ? dayTitle(day)
      : `${dayMonth(days[0])} – ${dayMonth(days[6])}`;
  // the export takes up to two months at once
  const exported = weekly
    ? { date_from: monday, branch_id: branch }
    : period === "month"
      ? { date_from: months[0].from, date_to: months[0].to, branch_id: branch }
      : null;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button isIconOnly aria-label="Назад" variant="flat" onPress={() => step(-1)}>
          <Icon name="chevron-left" />
        </Button>
        <div className="min-w-32 text-center text-base font-medium">{title}</div>
        <Button isIconOnly aria-label="Вперёд" variant="flat" onPress={() => step(1)}>
          <Icon name="chevron-right" />
        </Button>
        <Button color="primary" variant="flat" onPress={() => setDay(today)}>
          Сегодня
        </Button>
        <div aria-label="Период" className="flex rounded-xl bg-content1 p-1" role="group">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              aria-pressed={period === p.key}
              className={clsx(
                "min-h-9 rounded-lg px-3 text-sm",
                period === p.key ? "bg-primary/15 font-medium text-brand-text" : "text-default-600 hover:bg-default-100",
              )}
              type="button"
              onClick={() => setPeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        {exported && <ExportButton params={exported} path="/api/v1/rooms/schedule/export" />}
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
      {weekly ? (
        <QueryState empty={noRooms} isEmpty={(d) => d.rooms.length === 0} query={grid} skeleton={skeleton}>
          {(data) => {
            const shown = phone ? [day] : boardDays(days, data.lessons);

            return <Board days={shown} grid={data} hours={boardHours(data.lessons)} today={today} />;
          }}
        </QueryState>
      ) : (
        months.map((span) => <MonthBoards key={span.from} branch={branch} span={span} today={today} />)
      )}
    </>
  );
}
