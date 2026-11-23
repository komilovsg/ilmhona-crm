"use client";

import { type CSSProperties, useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { DateField } from "@/components/DateField";
import { ExportButton } from "@/components/ExportButton";
import { Icon } from "@/components/Icon";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { Segmented } from "@/components/Segmented";
import { SelectField } from "@/components/SelectField";
import { useCanChange } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dayMonth, dayTitle, mondayOf, todayIso, weekOf } from "@/lib/education";
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

import { type Slot, SlotActions } from "./SlotActions";

const LINE_PX = 5; // one TICK of the board: a half-hour row is 30px
const DAY_PX = 40; // the day row
const ROOM_PX = 28; // the room row

function Block({ lesson, style }: { lesson: GridLesson; style: CSSProperties }) {
  return (
    <Link
      className="lesson z-10 m-px overflow-hidden py-1 pl-2.5 pr-1.5 text-[11px] leading-[1.25] focus-visible:outline-2 focus-visible:outline-offset-1"
      href={`/cohorts/${lesson.cohort_id}`}
      style={{ ...style, "--h": courseHue(lesson.course_name) } as CSSProperties}
      title={[`${lesson.start}–${lesson.end}`, lesson.course_name, lesson.cohort_code, lesson.instructor_name]
        .filter(Boolean)
        .join(" · ")}
    >
      <div className="text-xs font-semibold [overflow-wrap:anywhere]">{lesson.course_name}</div>
      <div className="mt-0.5 truncate tabular-nums opacity-75">
        {lesson.start}–{lesson.end}
      </div>
      <div className="truncate opacity-75">{[lesson.cohort_code, lesson.instructor_name].filter(Boolean).join(" · ")}</div>
    </Link>
  );
}

/** «Пн 23.11»: the number leads, the weekday and the month are quiet. */
function DayTitle({ day, today }: { day: string; today: boolean }) {
  const [weekday, date] = dayTitle(day).split(" ");
  const [number, month] = date.split(".");

  return (
    <span className="sticky left-0 inline-flex items-baseline gap-1.5 px-3">
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-default-500">{weekday}</span>
      <span
        className={clsx(
          "text-sm font-semibold tabular-nums",
          today && "rounded-md bg-primary px-1.5 py-0.5 text-primary-foreground",
        )}
      >
        {number}
        {!today && <span className="font-normal text-default-400">.{month}</span>}
      </span>
    </span>
  );
}

/** Time down the side, a column per room inside each day; an empty cell is a free room. */
function Board({
  grid,
  days,
  today,
  hours,
  onPick,
}: {
  grid: ScheduleGrid;
  days: string[];
  today: string;
  hours: { from: number; to: number };
  /** a click on a free cell; absent for a user who cannot change cohorts */
  onPick?: (slot: Slot) => void;
}) {
  const rooms = grid.rooms;
  const lessons = grid.lessons.filter((l) => days.includes(l.date));
  const { from, to } = hours;
  const slots = slotsOf(from, to);
  const perSlot = SLOT / TICK;
  // each day is a block of its own: a narrow empty column follows its rooms
  const column = (day: number, room: number) => 1 + day * (rooms.length + 1) + room;
  const dayColumns = (day: number) => `${column(day, 0)} / span ${rooms.length}`;
  const HEAD = 2; // the day row and the room row
  const now = minutesNow();
  const nowLine = days.includes(today) && now >= from && now < to ? HEAD + Math.floor((now - from) / TICK) + 1 : null;

  return (
    <div className="surface-card flex overflow-hidden bg-content1 text-xs">
      {/* the hours stand still while the days scroll sideways */}
      <div aria-hidden className="w-12 shrink-0" style={{ paddingTop: DAY_PX + ROOM_PX }}>
        {slots.map((slot) => (
          <div
            key={slot}
            className="pr-2 text-right text-[11px] tabular-nums text-default-500"
            style={{ height: perSlot * LINE_PX }}
          >
            {/* the hour is named on its line; the half hour is only a tick of the grid */}
            {slot % 60 === 0 && <span className="relative -top-2">{clock(slot)}</span>}
          </div>
        ))}
      </div>
      <div className="min-w-0 flex-1 overflow-x-auto">
      <div
        className="grid"
        role="table"
        style={{
          gridTemplateColumns: `${days.map(() => `repeat(${rooms.length}, minmax(5.5rem, 1fr))`).join(" 0.75rem ")}`,
          gridTemplateRows: `${DAY_PX}px ${ROOM_PX}px repeat(${slots.length * perSlot}, ${LINE_PX}px)`,
        }}
      >
        {days.map((d, di) => (
          <div
            key={d}
            className={clsx(
              "flex items-center rounded-t-[10px] border border-b-0 border-[var(--hairline-strong)] bg-default-50",
            )}
            style={{ gridRow: 1, gridColumn: dayColumns(di) }}
          >
            {/* the day stays in sight while its rooms scroll by */}
            <DayTitle day={d} today={d === today} />
          </div>
        ))}
        {days.map((d, di) =>
          rooms.map((room, ri) => (
            <div
              key={`${d}-${room.id}`}
              className={clsx(
                "truncate border-b border-[var(--hairline-strong)] bg-default-50 px-1 text-center text-[11px] font-medium leading-7 text-default-600",
                "border-l border-l-[var(--hairline)]",
                ri === 0 && "border-l-[var(--hairline-strong)]",
                ri === rooms.length - 1 && "border-r border-r-[var(--hairline-strong)]",
              )}
              style={{ gridRow: 2, gridColumn: column(di, ri) }}
              title={`${room.name} · ${room.branch_name}`}
            >
              {room.name}
            </div>
          )),
        )}
        {/* the lines: one strip per half hour across, one per room down */}
        {days.map((d, di) =>
          slots.map((slot, si) => (
            <div
              key={`row-${d}-${slot}`}
              // the line under :00 is the half hour: lighter than the hour line
              className={clsx("border-b", slot % 60 === 0 ? "border-dashed border-[var(--hairline)]" : "border-[var(--hairline-strong)]")}
              style={{ gridColumn: dayColumns(di), gridRow: `${HEAD + 1 + si * perSlot} / span ${perSlot}` }}
            />
          )),
        )}
        {days.map((d, di) =>
          rooms.map((room, ri) => (
            <div
              key={`col-${d}-${room.id}`}
              className={clsx(
                "border-l border-l-[var(--hairline)]",
                ri === 0 && "border-l-[var(--hairline-strong)]",
                ri === rooms.length - 1 && "border-r border-r-[var(--hairline-strong)]",
                d === today && "bg-primary/[0.04]",
                onPick && "cursor-cell transition-colors hover:bg-primary/[0.08]",
              )}
              style={{ gridColumn: column(di, ri), gridRow: `${HEAD + 1} / -1` }}
              title={onPick ? `${room.name}: свободно — нажмите, чтобы занять` : undefined}
              onClick={
                onPick &&
                ((e) => {
                  const y = e.clientY - e.currentTarget.getBoundingClientRect().top;
                  const start = from + Math.floor(y / (perSlot * LINE_PX)) * SLOT;

                  onPick({ room, date: d, start: clock(Math.min(start, to - SLOT)), x: e.clientX, y: e.clientY });
                })
              }
            />
          )),
        )}
        {nowLine && (
          <div
            aria-hidden
            className="pointer-events-none z-10 border-t-2 border-danger"
            style={{ gridColumn: dayColumns(days.indexOf(today)), gridRow: nowLine }}
          />
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
    </div>
  );
}

/** Minutes since midnight in Dushanbe, whatever the browser's zone is. */
function minutesNow(): number {
  const [h, m] = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Dushanbe", hour: "2-digit", minute: "2-digit", hour12: false })
    .format(new Date())
    .split(":")
    .map(Number);

  return (h % 24) * 60 + m;
}

const skeleton = <Bone className="h-96 w-full rounded-2xl" />;
const noRooms = <EmptyState title="Нет аудиторий" />;

/** One month: its weeks one under another, each a board of its own. */
function MonthBoards({
  span,
  branch,
  today,
  onPick,
}: {
  span: MonthSpan;
  branch: string | null;
  today: string;
  onPick?: (slot: Slot) => void;
}) {
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
                  <Board days={boardDays(week, data.lessons)} grid={data} hours={hours} today={today} onPick={onPick} />
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
  const canChange = useCanChange("cohorts");
  const [slot, setSlot] = useState<Slot | null>(null);
  const onPick = canChange ? setSlot : undefined;
  const monday = mondayOf(day);
  const days = weekOf(day);
  const oneDay = period === "day" || (phone && period === "week");
  const weekly = period === "day" || period === "week";

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
  const step = (dir: -1 | 1) => setDay(shiftDay(oneDay ? "day" : period, day, dir));
  const title = !weekly
    ? periodTitle(period, day)
    : oneDay
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
        <Segmented label="Период" options={PERIODS} value={period} onChange={setPeriod} />
        <DateField filter className="w-40" label="Дата" value={day} onValueChange={(v) => v && setDay(v)} />
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
            const shown = oneDay ? [day] : boardDays(days, data.lessons);

            return <Board days={shown} grid={data} hours={boardHours(data.lessons)} today={today} onPick={onPick} />;
          }}
        </QueryState>
      ) : (
        months.map((span) => <MonthBoards key={span.from} branch={branch} span={span} today={today} onPick={onPick} />)
      )}
      {slot && <SlotActions key={`${slot.room.id}-${slot.date}-${slot.start}`} slot={slot} onClose={() => setSlot(null)} />}
    </>
  );
}
