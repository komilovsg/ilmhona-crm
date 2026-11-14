"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";

import { AcademyGoalBanner } from "@/components/goals/AcademyGoalBanner";
import { GoalsCard } from "@/components/goals/GoalsCard";
import { NotesCard } from "@/components/goals/NotesCard";
import { EmptyState } from "@/components/QueryState";
import type { LayoutCard } from "@/lib/dash";
import { AttentionCard, BranchMonthsCard, CoursesIncomeCard, DemandCard, MonthHeroCard, TimelineCard } from "./AdminCards";
import { CallQueueCard, QueuesCard, SeatsCard, WeekCard } from "./ManagerCards";
import { OverviewCard } from "./OverviewCard";

/** Every card the catalog can offer: full-width or not, and what renders it (given the branch toggle). */
const CARDS: Record<string, { full?: true; render: (branch: string) => ReactNode }> = {
  academy_goal: { full: true, render: () => <AcademyGoalBanner className="" /> },
  month_hero: { full: true, render: (b) => <MonthHeroCard branch={b} /> },
  goals: { render: () => <GoalsCard /> },
  demand: { render: (b) => <DemandCard branch={b} /> },
  timeline: { render: (b) => <TimelineCard branch={b} /> },
  attention: { render: (b) => <AttentionCard branch={b} /> },
  branches_months: { render: (b) => <BranchMonthsCard branch={b} /> },
  courses_income: { render: (b) => <CoursesIncomeCard branch={b} /> },
  notes: { full: true, render: () => <NotesCard /> },
  queues: { full: true, render: (b) => <QueuesCard branch={b} /> },
  call_queue: { render: (b) => <CallQueueCard branch={b} /> },
  seats: { render: (b) => <SeatsCard branch={b} /> },
  week: { full: true, render: (b) => <WeekCard branch={b} /> },
  overview: { full: true, render: (b) => <OverviewCard branch={b} /> },
};

const GAP = 24; // px: the row gap (md:gap-6) that the masonry spans add back

/**
 * A card in the two-column masonry of a wide screen: it reports its own height as `--span` (rows of
 * 1 px), so the grid packs a short card under a short one and nothing stretches to the height of its
 * row. On a phone the CSS ignores `--span`: one column, the user's order top to bottom.
 */
function MasonryItem({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;

    if (!el) return;
    const measure = () => el.style.setProperty("--span", String(Math.ceil(el.offsetHeight) + GAP));

    measure();
    const observer = new ResizeObserver(measure);

    observer.observe(el);

    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="min-w-0 empty:hidden">
      {children}
    </div>
  );
}

/**
 * The visible cards in the user's order. A hidden card is not rendered at all, so its queries never
 * run; an id this build does not know is skipped. Full-width cards stand alone; the cards between two
 * of them are packed in a masonry.
 */
export function CardsGrid({ branch, cards }: { branch: string; cards: LayoutCard[] }) {
  const shown = cards.filter((c) => c.visible && CARDS[c.id]);

  if (shown.length === 0)
    return <EmptyState hint="Нажмите «Настроить» и включите нужные карточки." title="Все карточки скрыты" />;

  const blocks: ({ full: LayoutCard } | { group: LayoutCard[] })[] = [];

  for (const c of shown) {
    const last = blocks.at(-1);

    if (CARDS[c.id].full) blocks.push({ full: c });
    else if (last && "group" in last) last.group.push(c);
    else blocks.push({ group: [c] });
  }

  return (
    <div className="flex flex-col gap-4 md:gap-6">
      {blocks.map((b) =>
        "full" in b ? (
          <div key={b.full.id} className="min-w-0 empty:hidden">
            {CARDS[b.full.id].render(branch)}
          </div>
        ) : (
          <div key={b.group[0].id} className="masonry grid grid-cols-1 gap-4 md:gap-6">
            {b.group.map((c) => (
              <MasonryItem key={c.id}>{CARDS[c.id].render(branch)}</MasonryItem>
            ))}
          </div>
        ),
      )}
    </div>
  );
}
