"use client";

import { useIsSuperadmin } from "@/hooks/goals";
import { AcademyGoalBanner } from "./AcademyGoalBanner";
import { GoalsCard } from "./GoalsCard";
import { NotesCard } from "./NotesCard";

/** Top of the dashboard: the academy goal for everybody, goals and private notes for the superadmin. */
export function DashboardTop() {
  const isSuperadmin = useIsSuperadmin();

  return (
    <>
      <AcademyGoalBanner />
      {isSuperadmin && (
        <div className="mb-4 grid gap-4">
          <GoalsCard />
          <NotesCard />
        </div>
      )}
    </>
  );
}
