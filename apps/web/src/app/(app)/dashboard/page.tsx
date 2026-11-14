"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@heroui/button";
import clsx from "clsx";

import { CardsGrid } from "@/components/dash/CardsGrid";
import { CustomizePanel } from "@/components/dash/CustomizePanel";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { Segmented } from "@/components/Segmented";
import { Bone } from "@/components/Skeletons";
import { useDashLayout } from "@/hooks/dash";
import { useBranches, useMe } from "@/hooks/queries";
import { useIsHydrated } from "@/lib/client-store";
import { weekdayDate } from "@/lib/dash";
import { dushanbeDay } from "@/lib/format";

function Skeleton(): ReactNode {
  return (
    <div className="grid gap-4 md:gap-6">
      <Bone className="h-14 w-full rounded-2xl" />
      <Bone className="h-48 w-full rounded-2xl" />
      <div className="grid gap-4 md:gap-6 lg:grid-cols-5">
        <Bone className="h-96 w-full rounded-2xl lg:col-span-3" />
        <Bone className="h-96 w-full rounded-2xl lg:col-span-2" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const layout = useDashLayout();
  const hydrated = useIsHydrated();
  const [branch, setBranch] = useState<string>("all");
  const [customizing, setCustomizing] = useState(false);
  const shown = me?.branch ? branches.filter((b) => b.id === me.branch?.id) : branches;
  const manager = me?.role.code !== "superadmin";
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
        <div className="flex flex-wrap items-center gap-2">
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
      <QueryState bare query={layout} skeleton={<Skeleton />}>
        {(l) => <CardsGrid branch={branch} cards={l.cards} />}
      </QueryState>
      {layout.data && <CustomizePanel isOpen={customizing} layout={layout.data} onOpenChange={setCustomizing} />}
    </div>
  );
}
