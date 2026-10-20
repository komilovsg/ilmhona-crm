"use client";

import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { UnfilledPanel } from "@/components/UnfilledPanel";
import { useCanSeeAttendance } from "@/hooks/attendance";

/** The dashboard comes with stage 4; until then it holds the «Не заполнено» widget (#21). */
export default function DashboardPage() {
  const seesAttendance = useCanSeeAttendance();

  return (
    <>
      <PageHeader title="Дашборд" />
      <div className="grid gap-4 lg:grid-cols-2">
        {seesAttendance && <UnfilledPanel />}
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-content1 px-6 py-12 text-center">
          <span className="rounded-full bg-primary/10 p-4 text-brand-text">
            <Icon name="dashboard" size={28} />
          </span>
          <h2 className="text-lg font-semibold">Скоро</h2>
          <p className="max-w-sm text-sm text-default-500">Показатели появятся в одном из следующих этапов.</p>
        </div>
      </div>
    </>
  );
}
