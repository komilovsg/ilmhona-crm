"use client";

import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";
import { Spinner } from "@heroui/spinner";

import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { SelectField } from "@/components/SelectField";
import { api } from "@/lib/api";
import { diffLines, type Names } from "@/lib/audit";
import { formatDateTime } from "@/lib/format";
import type { AuditPage, AuditRow, Paged, UserRow } from "@/lib/types";

const PAGE_SIZE = 25;

const ENTITIES = [
  { key: "app_user", label: "Пользователи" },
  { key: "role", label: "Роли" },
];

const ACTIONS: Record<string, string> = {
  "auth.login": "Вход",
  "auth.change_password": "Смена пароля",
  "profile.update": "Правка профиля",
  "user.create": "Создан пользователь",
  "user.update": "Изменён пользователь",
  "user.activate": "Активирован",
  "user.reset_password": "Сброшен пароль",
  "user.deactivate": "Заблокирован",
  "user.delete": "Удалён пользователь",
  "role.create": "Создана роль",
  "role.update": "Изменена роль",
  "role.delete": "Удалена роль",
};

type Filters = { user: string | null; entity: string | null; action: string | null };

function Diff({ diff, names, sections }: { diff: Record<string, unknown>; names: Names; sections: Names }) {
  const lines = diffLines(diff, names, sections);

  if (!lines.length) return <span className="text-default-500">—</span>;

  return (
    <ul className="space-y-0.5 text-xs">
      {lines.map((l, i) => (
        <li key={i} className="break-words">
          <span className="text-default-500">{l.label}:</span> {l.before} → {l.after}
        </li>
      ))}
    </ul>
  );
}

function FilterFields({ filters, set }: { filters: Filters; set: (f: Filters) => void }) {
  const picker = useQuery({
    queryKey: ["users", "picker"],
    queryFn: () => api<Paged<UserRow>>("/api/v1/users", { params: { page_size: "100" } }),
    staleTime: 60_000,
    // the audit page may be open to someone without the users section: the picker just stays empty
    retry: false,
  });

  return (
    <>
      <SelectField
        allLabel="Все пользователи"
        className="md:w-56"
        label="Кто"
        options={(picker.data?.items ?? []).map((u) => ({ key: u.id, label: u.full_name }))}
        value={filters.user}
        onChange={(user) => set({ ...filters, user })}
      />
      <SelectField
        allLabel="Всё"
        className="md:w-48"
        label="Объект"
        options={ENTITIES}
        value={filters.entity}
        onChange={(entity) => set({ ...filters, entity })}
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

export default function AuditPage() {
  const [filters, setFilters] = useState<Filters>({ user: null, entity: null, action: null });
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const list = useQuery({
    queryKey: ["audit", filters, page],
    queryFn: () =>
      api<AuditPage>("/api/v1/audit", {
        params: {
          user_id: filters.user ?? undefined,
          entity: filters.entity ?? undefined,
          action: filters.action ?? undefined,
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
  const activeFilters = Object.values(filters).filter(Boolean).length;
  const names = list.data?.names ?? {};
  const sections = list.data?.sections ?? {};
  const who = (r: AuditRow) => r.user_name ?? "Система";
  // «Изменён пользователь · Камол»: the action plus the entity it touched
  const what = (r: AuditRow) => {
    const target = r.entity_id ? names[r.entity_id] : undefined;
    const action = ACTIONS[r.action] ?? r.action;

    return target ? `${action} · ${target}` : action;
  };

  return (
    <>
      <PageHeader title="Журнал" />
      <div className="mb-4 flex items-center gap-3">
        <div className="hidden gap-3 md:flex">
          <FilterFields filters={filters} set={set} />
        </div>
        <Button className="md:hidden" startContent={<Icon name="filter" size={18} />} variant="flat" onPress={() => setFiltersOpen(true)}>
          Фильтры{activeFilters ? ` · ${activeFilters}` : ""}
        </Button>
      </div>

      {list.isPending ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">Записей нет.</p>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Время</th>
                  <th className="px-4 py-3 font-medium">Кто</th>
                  <th className="px-4 py-3 font-medium">Действие</th>
                  <th className="px-4 py-3 font-medium">Что изменилось</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-divider align-top last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 text-default-600">{formatDateTime(r.at)}</td>
                    <td className="px-4 py-3">{who(r)}</td>
                    <td className="px-4 py-3">{what(r)}</td>
                    <td className="px-4 py-3">
                      <Diff diff={r.diff} names={names} sections={sections} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-3 md:hidden">
            {rows.map((r) => (
              <li key={r.id} className="rounded-2xl bg-content1 p-4">
                <div className="flex justify-between gap-2 text-xs text-default-500">
                  <span>{formatDateTime(r.at)}</span>
                  <span>{who(r)}</span>
                </div>
                <div className="mt-1 font-medium">{what(r)}</div>
                <div className="mt-2">
                  <Diff diff={r.diff} names={names} sections={sections} />
                </div>
              </li>
            ))}
          </ul>
          <Pager page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onChange={setPage} />
        </>
      )}

      <Drawer isOpen={filtersOpen} placement="bottom" onOpenChange={setFiltersOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <DrawerHeader>Фильтры</DrawerHeader>
              <DrawerBody className="gap-3">
                <FilterFields filters={filters} set={set} />
              </DrawerBody>
              <DrawerFooter>
                <Button variant="light" onPress={() => set({ user: null, entity: null, action: null })}>
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
