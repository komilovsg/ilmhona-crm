"use client";

import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";
import { Input } from "@heroui/input";


import { ExportButton } from "@/components/ExportButton";
import { FillBar } from "@/components/FillBar";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { EmptyState, QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { CardGridSkeleton, PillsSkeleton } from "@/components/Skeletons";
import { CohortStatus } from "@/components/StatusChip";
import { useCanChange, useEducationSummary } from "@/hooks/education";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { COHORT_STATUSES, daysLabel, fullDate } from "@/lib/education";
import type { CohortRow, Paged } from "@/lib/types";
import { useOverlayMotion } from "@/lib/motion";

const CohortFormModal = dynamic(() => import("./CohortFormModal").then((m) => m.CohortFormModal));

const PAGE_SIZE = 12;
type Filters = { q: string; status: string | null; branch: string | null };

function FilterFields({ filters, set }: { filters: Filters; set: (f: Filters) => void }) {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();

  return (
    <>
      <SelectField
        allLabel="Любой статус"
        className="md:w-44"
        label="Статус"
        options={COHORT_STATUSES.map((s) => ({ key: s, label: s }))}
        value={filters.status}
        onChange={(status) => set({ ...filters, status })}
      />
      {!me?.branch && (
        <SelectField
          allLabel="Все филиалы"
          className="md:w-48"
          label="Филиал"
          options={branches.map((b) => ({ key: b.id, label: b.name }))}
          value={filters.branch}
          onChange={(branch) => set({ ...filters, branch })}
        />
      )}
    </>
  );
}

function CohortCard({ cohort: c }: { cohort: CohortRow }) {
  return (
    <Link
      className="flex flex-col gap-3 rounded-2xl bg-content1 p-4 transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-primary"
      href={`/cohorts/${c.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-medium text-brand-text">{c.code}</div>
          <div className="truncate text-base font-semibold">{c.course_name}</div>
        </div>
        <CohortStatus status={c.status} />
      </div>
      <dl className="grid gap-1.5 text-sm">
        <div className="flex items-center gap-2 text-default-600">
          <Icon name="instructors" size={14} />
          <dd className="truncate">{c.instructor_name ?? "Инструктор не назначен"}</dd>
        </div>
        <div className="flex items-center gap-2 text-default-600">
          <Icon name="calendar" size={14} />
          <dd>
            {fullDate(c.start_date)} – {fullDate(c.end_date)}
          </dd>
        </div>
        <div className="flex items-center gap-2 text-default-600">
          <Icon name="clock" size={14} />
          <dd>
            {daysLabel(c.weekdays)} · {c.start_time}–{c.end_time}
          </dd>
        </div>
        <div className="flex items-center gap-2 text-default-600">
          <Icon name="rooms" size={14} />
          <dd className="truncate">
            {c.room_name} · {c.branch_name}
          </dd>
        </div>
      </dl>
      <FillBar fill={c.fill} />
    </Link>
  );
}

export default function CohortsPage() {
  const overlayMotion = useOverlayMotion();
  const canChange = useCanChange("cohorts");
  const summary = useEducationSummary();
  const [filters, setFilters] = useState<Filters>({ q: "", status: null, branch: null });
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const list = useQuery({
    queryKey: ["cohorts", filters, page],
    queryFn: () =>
      api<Paged<CohortRow>>("/api/v1/cohorts", {
        params: {
          q: filters.q.trim() || undefined,
          status: filters.status ?? undefined,
          branch_id: filters.branch ?? undefined,
          page: String(page),
          page_size: String(PAGE_SIZE),
        },
      }),
    placeholderData: keepPreviousData,
  });

  const set = (next: Filters) => {
    setFilters(next);
    setPage(1);
  };
  const cohorts = list.data?.items ?? [];
  const activeFilters = [filters.status, filters.branch].filter(Boolean).length;
  const counts = summary.data?.cohorts;

  return (
    <>
      <PageHeader
        actions={
          <>
            <ExportButton
              params={{ q: filters.q.trim(), status: filters.status, branch_id: filters.branch }}
              path="/api/v1/cohorts/export"
            />
            {canChange && (
              <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setCreating(true)}>
                Поток
              </Button>
            )}
          </>
        }
        title="Потоки"
      />

      {!counts && <PillsSkeleton />}
      {counts && (
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <span className="rounded-full bg-content1 px-3 py-1">
            Активных: <b>{summary.data?.active_cohorts}</b>
          </span>
          <span className="rounded-full bg-content1 px-3 py-1">
            Набор: <b>{counts["набор"]}</b>
          </span>
          <span className="rounded-full bg-content1 px-3 py-1">
            Завершённых: <b>{counts["завершён"]}</b>
          </span>
          <span className="rounded-full bg-content1 px-3 py-1">
            Всего: <b>{counts["всего"]}</b>
          </span>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          className="flex-1 md:max-w-xs md:flex-none"
          isClearable
          placeholder="Поиск: код, курс, инструктор"
          startContent={<Icon name="search" size={18} />}
          value={filters.q}
          onClear={() => set({ ...filters, q: "" })}
          onValueChange={(q) => set({ ...filters, q })}
        />
        <div className="hidden gap-3 md:flex">
          <FilterFields filters={filters} set={set} />
        </div>
        <Button className="md:hidden" startContent={<Icon name="filter" size={18} />} variant="flat" onPress={() => setFiltersOpen(true)}>
          Фильтры{activeFilters ? ` · ${activeFilters}` : ""}
        </Button>
      </div>

      <QueryState
        empty={
          <EmptyState
            action={
              canChange && activeFilters === 0 && !filters.q.trim() ? (
                <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setCreating(true)}>
                  Поток
                </Button>
              ) : undefined
            }
            hint={activeFilters || filters.q.trim() ? "Измените поиск или фильтры." : undefined}
            title={activeFilters || filters.q.trim() ? "Потоков не найдено" : "Нет потоков"}
          />
        }
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={<CardGridSkeleton />}
      >
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {cohorts.map((c) => (
              <CohortCard key={c.id} cohort={c} />
            ))}
          </div>
          <Pager page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onChange={setPage} />
        </>
      </QueryState>

      <Drawer isOpen={filtersOpen} motionProps={overlayMotion} placement="bottom" onOpenChange={setFiltersOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <DrawerHeader>Фильтры</DrawerHeader>
              <DrawerBody className="gap-3">
                <FilterFields filters={filters} set={set} />
              </DrawerBody>
              <DrawerFooter>
                <Button variant="light" onPress={() => set({ ...filters, status: null, branch: null })}>
                  Сбросить
                </Button>
                <Button color="primary" onPress={close}>
                  Показать
                </Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      {creating && <CohortFormModal cohort={null} onClose={() => setCreating(false)} />}
    </>
  );
}
