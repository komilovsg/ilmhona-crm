"use client";

import { useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader } from "@heroui/drawer";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";
import { Input } from "@heroui/input";
import { Spinner } from "@heroui/spinner";

import { UserFormModal } from "./UserFormModal";

import { ConfirmModal } from "@/components/ConfirmModal";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Pager } from "@/components/Pager";
import { SelectField } from "@/components/SelectField";
import { TempPasswordModal } from "@/components/TempPasswordModal";
import { useBranches, useMe, useRoles } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { notify, notifyError } from "@/lib/toast";
import type { Paged, TempPassword, UserRow } from "@/lib/types";

const PAGE_SIZE = 25;
type Filters = { q: string; branch: string | null; role: string | null; status: string | null };
type Action = { kind: "activate" | "deactivate" | "delete"; user: UserRow };

function StatusChip({ user }: { user: UserRow }) {
  if (!user.is_active) return <Chip size="sm">Заблокирован</Chip>;
  if (user.must_change_password)
    return (
      <Chip color="warning" size="sm" variant="flat">
        Ждёт входа
      </Chip>
    );

  return (
    <Chip color="success" size="sm" variant="flat">
      Активен
    </Chip>
  );
}

function RowMenu({ user, onEdit, onAction }: { user: UserRow; onEdit: () => void; onAction: (a: Action["kind"]) => void }) {
  return (
    <Dropdown placement="bottom-end">
      <DropdownTrigger>
        <Button isIconOnly aria-label={`Действия: ${user.full_name}`} size="sm" variant="light">
          <Icon name="more" />
        </Button>
      </DropdownTrigger>
      <DropdownMenu
        aria-label="Действия"
        disabledKeys={user.is_active ? [] : ["deactivate"]}
        onAction={(key) => (key === "edit" ? onEdit() : onAction(key as Action["kind"]))}
      >
        <DropdownItem key="edit" startContent={<Icon name="edit" size={16} />}>
          Изменить
        </DropdownItem>
        <DropdownItem key="activate" startContent={<Icon name="key" size={16} />}>
          {user.is_active && !user.must_change_password ? "Сбросить пароль" : "Активировать / сбросить пароль"}
        </DropdownItem>
        <DropdownItem key="deactivate" startContent={<Icon name="ban" size={16} />}>
          Заблокировать
        </DropdownItem>
        <DropdownItem key="delete" className="text-danger" color="danger" startContent={<Icon name="trash" size={16} />}>
          Удалить
        </DropdownItem>
      </DropdownMenu>
    </Dropdown>
  );
}

function FilterFields({ filters, set }: { filters: Filters; set: (f: Filters) => void }) {
  const { data: me } = useMe();
  const { data: branches = [] } = useBranches();
  const { data: roles = [] } = useRoles();

  return (
    <>
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
        allLabel="Все роли"
        className="md:w-52"
        label="Роль"
        options={roles.map((r) => ({ key: r.id, label: r.name }))}
        value={filters.role}
        onChange={(role) => set({ ...filters, role })}
      />
      <SelectField
        allLabel="Любой статус"
        className="md:w-44"
        label="Статус"
        options={[
          { key: "true", label: "Активные" },
          { key: "false", label: "Заблокированные" },
        ]}
        value={filters.status}
        onChange={(status) => set({ ...filters, status })}
      />
    </>
  );
}

export default function UsersPage() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canChange = can(me?.permissions, "users", "change");
  const [filters, setFilters] = useState<Filters>({ q: "", branch: null, role: null, status: null });
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [temp, setTemp] = useState<{ login: string; password: string; expiresAt: string | null | undefined } | null>(null);

  const list = useQuery({
    queryKey: ["users", filters, page],
    queryFn: () =>
      api<Paged<UserRow>>("/api/v1/users", {
        params: {
          q: filters.q.trim() || undefined,
          branch_id: filters.branch ?? undefined,
          role_id: filters.role ?? undefined,
          is_active: filters.status ?? undefined,
          page: String(page),
          page_size: String(PAGE_SIZE),
        },
      }),
    placeholderData: keepPreviousData,
  });

  const run = useMutation({
    mutationFn: async ({ kind, user }: Action): Promise<TempPassword | null> => {
      if (kind === "activate") return api<TempPassword>(`/api/v1/users/${user.id}/activate`, { method: "POST" });
      if (kind === "deactivate") await api(`/api/v1/users/${user.id}/deactivate`, { method: "POST" });
      else await api(`/api/v1/users/${user.id}`, { method: "DELETE" });

      return null;
    },
    onSuccess: (result, { kind, user }) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      void queryClient.invalidateQueries({ queryKey: ["roles"] });
      setAction(null);
      if (result) {
        setTemp({ login: user.login, password: result.temp_password, expiresAt: result.expires_at });
      } else notify(kind === "delete" ? "Пользователь удалён" : "Пользователь заблокирован");
    },
    onError: (e) => {
      setAction(null);
      notifyError(e);
    },
  });

  const set = (next: Filters) => {
    setFilters(next);
    setPage(1);
  };
  const users = list.data?.items ?? [];
  const activeFilters = [filters.branch, filters.role, filters.status].filter(Boolean).length;
  const menu = (u: UserRow) =>
    canChange && <RowMenu user={u} onAction={(kind) => setAction({ kind, user: u })} onEdit={() => setEditing(u)} />;

  return (
    <>
      <PageHeader
        actions={
          canChange && (
            <Button color="primary" startContent={<Icon name="plus" size={18} />} onPress={() => setEditing("new")}>
              Пользователь
            </Button>
          )
        }
        title="Пользователи"
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          className="flex-1 md:max-w-xs md:flex-none"
          isClearable
          placeholder="Поиск: логин, ФИО, телефон"
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

      {list.isPending ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : users.length === 0 ? (
        <p className="rounded-2xl bg-content1 p-8 text-center text-default-500">Никого не найдено.</p>
      ) : (
        <>
          <div className="hidden overflow-hidden rounded-2xl bg-content1 md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-divider text-xs text-default-500">
                <tr>
                  <th className="px-4 py-3 font-medium">ФИО</th>
                  <th className="px-4 py-3 font-medium">Логин</th>
                  <th className="px-4 py-3 font-medium">Роль</th>
                  <th className="px-4 py-3 font-medium">Филиал</th>
                  <th className="px-4 py-3 font-medium">Телефон</th>
                  <th className="px-4 py-3 font-medium">Статус</th>
                  <th className="w-12" />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-divider last:border-0 hover:bg-default-50">
                    <td className="px-4 py-3 font-medium">{u.full_name}</td>
                    <td className="px-4 py-3 text-default-600">{u.login}</td>
                    <td className="px-4 py-3">{u.role_name}</td>
                    <td className="px-4 py-3">{u.branch_name ?? "Все"}</td>
                    <td className="px-4 py-3">
                      {u.phone ? (
                        <a className="text-brand-text" href={`tel:${u.phone}`}>
                          {u.phone}
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusChip user={u} />
                      {u.must_change_password && u.temp_password_expires_at && (
                        <div className="mt-1 text-xs text-default-500">до {formatDateTime(u.temp_password_expires_at)}</div>
                      )}
                    </td>
                    <td className="px-2">{menu(u)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="space-y-3 md:hidden">
            {users.map((u) => (
              <li key={u.id} className="rounded-2xl bg-content1 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{u.full_name}</div>
                    <div className="text-sm text-default-500">{u.login}</div>
                  </div>
                  {menu(u)}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                  <StatusChip user={u} />
                  <span>{u.role_name}</span>
                  <span className="text-default-500">· {u.branch_name ?? "Все филиалы"}</span>
                </div>
                {u.phone && (
                  <a className="mt-2 inline-flex items-center gap-1.5 text-sm text-brand-text" href={`tel:${u.phone}`}>
                    <Icon name="phone" size={14} />
                    {u.phone}
                  </a>
                )}
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
                <Button
                  variant="light"
                  onPress={() => set({ ...filters, branch: null, role: null, status: null })}
                >
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

      {editing && (
        <UserFormModal
          user={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onCreated={(r) => setTemp({ login: r.user.login, password: r.temp_password, expiresAt: r.user.temp_password_expires_at })}
        />
      )}
      {temp && <TempPasswordModal {...temp} onClose={() => setTemp(null)} />}
      {action && (
        <ConfirmModal
          confirmLabel={
            action.kind === "activate" ? "Выдать пароль" : action.kind === "deactivate" ? "Заблокировать" : "Удалить"
          }
          danger={action.kind !== "activate"}
          isLoading={run.isPending}
          isOpen
          title={
            action.kind === "activate"
              ? "Активировать или сбросить пароль"
              : action.kind === "deactivate"
                ? "Заблокировать пользователя"
                : "Удалить пользователя"
          }
          onClose={() => setAction(null)}
          onConfirm={() => run.mutate(action)}
        >
          {action.kind === "activate" &&
            `Для ${action.user.full_name} будет создан новый временный пароль на 7 дней, старый перестанет работать, открытые сеансы закроются.`}
          {action.kind === "deactivate" &&
            `${action.user.full_name} не сможет войти, открытые сеансы закроются. Данные сохранятся.`}
          {action.kind === "delete" &&
            `${action.user.full_name} будет удалён безвозвратно. Если с ним связаны данные, лучше заблокировать.`}
        </ConfirmModal>
      )}
    </>
  );
}
