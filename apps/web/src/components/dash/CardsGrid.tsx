"use client";

import type { ReactNode } from "react";
import clsx from "clsx";

import { AcademyGoalBanner } from "@/components/goals/AcademyGoalBanner";
import { GoalsCard } from "@/components/goals/GoalsCard";
import { NotesCard } from "@/components/goals/NotesCard";
import { EmptyState } from "@/components/QueryState";
import type { LayoutCard } from "@/lib/dash";
import { AttentionCard, BranchMonthsCard, CoursesIncomeCard, DemandCard, MonthHeroCard, TimelineCard } from "./AdminCards";
import { CallQueueCard, QueuesCard, SeatsCard, WeekCard } from "./ManagerCards";
import { OverviewCard } from "./OverviewCard";

type Span = "full" | "wide" | "narrow";

const SPAN: Record<Span, string> = {
  full: "lg:col-span-5",
  wide: "lg:col-span-3",
  narrow: "lg:col-span-2",
};

/** Every card the catalog can offer: its width on a wide screen and what renders it (given the branch toggle). */
const CARDS: Record<string, { span: Span; render: (branch: string) => ReactNode }> = {
  academy_goal: { span: "full", render: () => <AcademyGoalBanner className="" /> },
  month_hero: { span: "full", render: (b) => <MonthHeroCard branch={b} /> },
  goals: { span: "wide", render: () => <GoalsCard /> },
  demand: { span: "narrow", render: (b) => <DemandCard branch={b} /> },
  timeline: { span: "wide", render: (b) => <TimelineCard branch={b} /> },
  attention: { span: "narrow", render: (b) => <AttentionCard branch={b} /> },
  branches_months: { span: "wide", render: (b) => <BranchMonthsCard branch={b} /> },
  courses_income: { span: "narrow", render: (b) => <CoursesIncomeCard branch={b} /> },
  notes: { span: "full", render: () => <NotesCard /> },
  queues: { span: "full", render: (b) => <QueuesCard branch={b} /> },
  call_queue: { span: "wide", render: (b) => <CallQueueCard branch={b} /> },
  seats: { span: "narrow", render: (b) => <SeatsCard branch={b} /> },
  week: { span: "full", render: (b) => <WeekCard branch={b} /> },
  overview: { span: "full", render: (b) => <OverviewCard branch={b} /> },
};

/**
 * The visible cards in the user's order. A hidden card is not rendered at all, so its queries never
 * run; an id this build does not know is skipped.
 */
export function CardsGrid({ branch, cards }: { branch: string; cards: LayoutCard[] }) {
  const shown = cards.filter((c) => c.visible && CARDS[c.id]);

  if (shown.length === 0)
    return <EmptyState hint="Нажмите «Настроить» и включите нужные карточки." title="Все карточки скрыты" />;

  return (
    <div className="grid grid-cols-1 items-start gap-4 md:gap-6 lg:grid-cols-5">
      {shown.map((c) => (
        <div key={c.id} className={clsx("min-w-0 empty:hidden", SPAN[CARDS[c.id].span])}>
          {CARDS[c.id].render(branch)}
        </div>
      ))}
    </div>
  );
}
