"use client";

import { useDeferredValue, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";
import { SheetHandle } from "@/components/SheetHandle";
import { Input } from "@heroui/input";
import Link from "next/link";

import { Icon } from "@/components/Icon";
import { ExportButton } from "@/components/ExportButton";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, QueryState } from "@/components/QueryState";
import { Bone } from "@/components/Skeletons";
import { Pager } from "@/components/Pager";
import { SelectField } from "@/components/SelectField";
import { useBranches, useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { groupByDay, linkHref, timeOf } from "@/lib/audit";
import type { AuditPage, AuditRow, Paged, UserRow } from "@/lib/types";
import { useOverlayMotion } from "@/lib/motion";

const PAGE_SIZE = 25;

const ACTIONS: Record<string, string> = {
  "auth.login": "Вход",
  "auth.login_failed": "Неудачный вход",
  "auth.locked": "Блокировка логина",
  "auth.change_password": "Смена пароля",
  "profile.update": "Правка профиля",
  "student.create": "Студент создан",
  "student.update": "Студент изменён",
  "student.delete": "Студент удалён",
  "enrollment.create": "Зачисление",
  "enrollment.update": "Статус зачисления",
  "enrollment.delete": "Студент убран из потока",
  "cohort.create": "Поток создан",
  "cohort.update": "Поток изменён",
  "cohort.cancel": "Поток отменён",
  "cohort.restore": "Поток восстановлен",
  "cohort.delete": "Поток удалён",
  "lesson.create": "Урок добавлен",
  "lesson.move": "Урок перенесён",
  "lesson.cancel": "Урок отменён",
  "room.create": "Аудитория создана",
  "room.update": "Аудитория изменена",
  "room.delete": "Аудитория удалена",
  "course.create": "Курс создан",
  "course.update": "Курс изменён",
  "course.delete": "Курс удалён",
  "user.create": "Пользователь создан",
  "user.update": "Пользователь изменён",
  "user.activate": "Пользователь активирован",
  "user.reset_password": "Сброшен пароль",
  "user.deactivate": "Пользователь заблокирован",
  "user.delete": "Пользователь удалён",
  "role.create": "Роль создана",
  "role.update": "Роль изменена",
  "role.delete": "Роль удалена",
};

type Filters = {
  from: string;
  to: string;
  section: string | null;
  branch: string | null;
  user: string | null;
  action: string | null;
  q: string;
};

const NO_FILTERS: Filters = { from: "", to: "", section: null, branch: null, user: null, action: null, q: "" };

function FilterFields({
  filters,
  set,
  sections,
}: {
  filters: Filters;
  set: (f: Filters) => void;
  sections: Record<string, string>;
}) {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const picker = useQuery({
    queryKey: ["users", "picker"],
    queryFn: () => api<Paged<UserRow>>("/api/v1/users", { params: { page_size: "100" } }),
    staleTime: 60_000,
    // the audit page may be open to someone without the users section: the picker just stays empty
    retry: false,
  });
  const sectionOptions = Object.entries(sections)
    .filter(([key]) => ["auth", "students", "cohorts", "rooms", "users"].includes(key))
    .map(([key, label]) => ({ key, label }));

  return (
    <>
      <Input
        className="md:w-44"
        label="С даты"
        placeholder=" "
        type="date"
        value={filters.from}
        onValueChange={(from) => set({ ...filters, from })}
      />
      <Input
        className="md:w-44"
        label="По дату"
        placeholder=" "
        type="date"
        value={filters.to}
        onValueChange={(to) => set({ ...filters, to })}
      />
      <SelectField
        allLabel="Все разделы"
        className="md:w-48"
        label="Раздел"
        options={sectionOptions}
        value={filters.section}
        onChange={(section) => set({ ...filters, section })}
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
      <SelectField
        allLabel="Все пользователи"
        className="md:w-56"
        label="Кто"
        options={(picker.data?.items ?? []).map((u) => ({ key: u.id, label: u.full_name }))}
        value={filters.user}
        onChange={(user) => set({ ...filters, user })}
      />
      <SelectField
        allLabel="Любое действие"
        className="md:w-56"
        label="Действие"
        options={Object.entries(ACTIONS).map(([key, label]) => ({ key, label }))}
        value={filters.action}
        onChange={(action) => set({ ...filters, action })}
      />
    </>
  );
}

function Entry({ row }: { row: AuditRow }) {
  const href = linkHref(row.link);
  const body = (
    <>
      <span className="w-12 shrink-0 text-xs tabular-nums text-default-500 md:pt-0.5">{timeOf(row.at)}</span>
      <span className="min-w-0 flex-1 break-words text-sm">{row.text}</span>
    </>
  );
  const layout = "flex gap-3 max-md:flex-col max-md:gap-1";

  return (
    <li className="rounded-2xl bg-content1 md:rounded-none">
      {href ? (
        <Link className={`${layout} p-4 transition-colors hover:bg-default-100 md:py-3`} href={href}>
          {body}
        </Link>
      ) : (
        <div className={`${layout} p-4 md:py-3`}>{body}</div>
      )}
    </li>
  );
}

export default function AuditPage() {
  const overlayMotion = useOverlayMotion();
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const q = useDeferredValue(filters.q.trim());
  const list = useQuery({
    queryKey: ["audit", { ...filters, q }, page],
    queryFn: () =>
      api<AuditPage>("/api/v1/audit", {
        params: {
          date_from: filters.from || undefined,
          date_to: filters.to || undefined,
          section: filters.section ?? undefined,
          branch_id: filters.branch ?? undefined,
          user_id: filters.user ?? undefined,
          action: filters.action ?? undefined,
          q: q || undefined,
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
  const rows = list.data?.items ?? [];
  const sections = list.data?.sections ?? {};
  const activeFilters = Object.entries(filters).filter(([k, v]) => k !== "q" && v).length;
  const groups = groupByDay(rows);

  return (
    <>
      <PageHeader
        actions={
          <ExportButton
            params={{
              date_from: filters.from,
              date_to: filters.to,
              section: filters.section,
              branch_id: filters.branch,
              user_id: filters.user,
              action: filters.action,
              q,
            }}
            path="/api/v1/audit/export"
          />
        }
        title="Журнал"
      />
      <div className="mb-4 flex items-center gap-3">
        <Input
          isClearable
          className="min-w-0 flex-1 md:max-w-sm"
          label="Поиск"
          startContent={<Icon name="search" size={18} />}
          value={filters.q}
          onClear={() => set({ ...filters, q: "" })}
          onValueChange={(v) => set({ ...filters, q: v })}
        />
        <Button className="md:hidden" startContent={<Icon name="filter" size={18} />} variant="flat" onPress={() => setFiltersOpen(true)}>
          Фильтры{activeFilters ? ` · ${activeFilters}` : ""}
        </Button>
      </div>
      <div className="mb-4 hidden flex-wrap gap-3 md:flex">
        <FilterFields filters={filters} set={set} sections={sections} />
        {activeFilters > 0 && (
          <Button variant="light" onPress={() => set({ ...NO_FILTERS, q: filters.q })}>
            Сбросить
          </Button>
        )}
      </div>

      <QueryState
        empty={<EmptyState title="Записей нет" />}
        isEmpty={(d) => d.items.length === 0}
        query={list}
        skeleton={
          <div>
            <Bone className="mb-2 h-5 w-24" />
            <ul className="divide-y divide-divider overflow-hidden rounded-2xl bg-content1">
              {Array.from({ length: 8 }, (_, i) => (
                <li key={i} className="px-4 py-3">
                  <Bone className="h-5 w-2/3" />
                </li>
              ))}
            </ul>
          </div>
        }
      >
        <>
          {groups.map((g) => (
            <section key={g.day} className="mb-5">
              <h2 className="mb-2 text-sm font-medium text-default-600">{g.label}</h2>
              <ul className="space-y-2 md:divide-y md:divide-divider md:space-y-0 md:overflow-hidden md:rounded-2xl md:bg-content1">
                {g.items.map((r) => (
                  <Entry key={r.id} row={r} />
                ))}
              </ul>
            </section>
          ))}
          <Pager page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onChange={setPage} />
        </>
      </QueryState>

      <Drawer isOpen={filtersOpen} motionProps={overlayMotion} placement="bottom" onOpenChange={setFiltersOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <SheetHandle onClose={close} />
              <DrawerHeader>Фильтры</DrawerHeader>
              <DrawerBody className="gap-3">
                <FilterFields filters={filters} set={set} sections={sections} />
              </DrawerBody>
              <DrawerFooter>
                <Button variant="light" onPress={() => set({ ...NO_FILTERS, q: filters.q })}>
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
    </>
  );
}
