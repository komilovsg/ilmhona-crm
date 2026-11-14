"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { CardsGrid } from "@/components/dash/CardsGrid";
import { DashPageSkeleton } from "@/components/dash/PageSkeleton";
import { CustomizePanel } from "@/components/dash/CustomizePanel";
import { Icon } from "@/components/Icon";
import { Late } from "@/components/Skeletons";
import { QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { useDashLayout } from "@/hooks/dash";
import { useAcademyGoal } from "@/hooks/goals";
import { useBranches, useMe } from "@/hooks/queries";
import { useIsHydrated } from "@/lib/client-store";
import { weekdayDate } from "@/lib/dash";
import { dushanbeDay } from "@/lib/format";

export default function DashboardPage() {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const layout = useDashLayout();
  // asked together with the layout, so the banner has its answer when the cards appear (no shift)
  const goal = useAcademyGoal();
  const hydrated = useIsHydrated();
  const [branch, setBranch] = useState<string>("all");
  const [customizing, setCustomizing] = useState(false);
  const shown = me?.branch ? branches.filter((b) => b.id === me.branch?.id) : branches;
  const manager = me ? me.role.code !== "superadmin" : false;
  const branchName = branch === "all" ? (me?.branch?.name ?? "Все филиалы") : (branches.find((b) => b.id === branch)?.name ?? "");

  return (
    <div className="mx-auto flex max-w-[80rem] flex-col gap-4 md:gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className={clsx("min-h-4 text-[0.8125rem] leading-4 text-default-500", !hydrated && "invisible")}>
            {branchName} · {hydrated ? weekdayDate(dushanbeDay(new Date().toISOString())) : "…"}
          </span>
          <h1 className="font-display text-[1.75rem] font-bold leading-9">{manager ? "Мой день" : "Дашборд"}</h1>
        </div>
        <div className="grid w-full gap-2 md:flex md:w-auto md:items-center">
          {(!me?.branch || shown.length > 1) && (
            <Segmented
              label="Филиал"
              options={[{ key: "all", label: "Все" }, ...shown.map((b) => ({ key: b.id, label: b.name }))]}
              value={branch}
              onChange={setBranch}
            />
          )}
          <Button
            isDisabled={!layout.data}
            startContent={<Icon name="sliders" size={18} />}
            variant="flat"
            onPress={() => setCustomizing(true)}
          >
            Настроить
          </Button>
        </div>
      </div>
      {goal.isPending && !layout.isError ? (
        <div aria-busy="true" role="status">
          <span className="sr-only">Загрузка…</span>
          <Late>
            <DashPageSkeleton manager={manager} />
          </Late>
        </div>
      ) : (
        <QueryState bare query={layout} skeleton={<DashPageSkeleton manager={manager} />}>
          {(l) => <CardsGrid branch={branch} cards={l.cards} />}
        </QueryState>
      )}
      {layout.data && <CustomizePanel isOpen={customizing} layout={layout.data} onOpenChange={setCustomizing} />}
    </div>
  );
}
