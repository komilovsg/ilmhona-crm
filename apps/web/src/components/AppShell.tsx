"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerHeader } from "@heroui/drawer";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";
import { Spinner } from "@heroui/spinner";

import { Icon } from "./Icon";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

import { useMe } from "@/hooks/queries";
import { api } from "@/lib/api";
import { canOpen, splitNav, visibleNav, type NavItem } from "@/lib/permissions";
import type { Me } from "@/lib/types";

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function useLogout() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return async () => {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    queryClient.clear();
    router.replace("/login");
  };
}

function Sidebar({ items, pathname }: { items: NavItem[]; pathname: string }) {
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col bg-sidebar md:flex">
      <div className="px-6 py-6">
        <Logo />
      </div>
      <nav aria-label="Разделы" className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-6">
        {items.map((item) => {
          const active = isActive(pathname, item.href);

          return (
            <Link
              key={item.href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                active ? "bg-[#00A0DC]/15 text-[#38BDF0]" : "text-[#aab5bf] hover:bg-white/5 hover:text-white"
              }`}
              href={item.href}
            >
              <Icon name={item.icon} size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

function UserMenu({ me }: { me: Me }) {
  const logout = useLogout();
  const router = useRouter();

  return (
    <Dropdown placement="bottom-end">
      <DropdownTrigger>
        <Button className="max-w-56" radius="full" variant="flat" startContent={<Icon name="profile" size={16} />}>
          <span className="truncate">{me.full_name}</span>
        </Button>
      </DropdownTrigger>
      <DropdownMenu
        aria-label="Пользователь"
        onAction={(key) => {
          if (key === "profile") router.push("/profile");
          if (key === "logout") void logout();
        }}
      >
        <DropdownItem key="info" isReadOnly className="opacity-100" textValue="Роль">
          <div className="text-xs text-default-500">
            {me.role.name}
            {me.branch ? ` · ${me.branch.name}` : " · все филиалы"}
          </div>
        </DropdownItem>
        <DropdownItem key="profile">Профиль</DropdownItem>
        <DropdownItem key="logout" className="text-danger" color="danger">
          Выйти
        </DropdownItem>
      </DropdownMenu>
    </Dropdown>
  );
}

function BottomNav({ main, more, pathname }: { main: NavItem[]; more: NavItem[]; pathname: string }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const logout = useLogout();
  const moreActive = more.some((i) => isActive(pathname, i.href)) || pathname === "/profile";
  const tab = (active: boolean) =>
    `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] ${active ? "text-brand-text" : "text-default-500"}`;

  return (
    <>
      <nav
        aria-label="Основное меню"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-divider bg-content1 pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {main.map((item) => (
          <Link key={item.href} className={tab(isActive(pathname, item.href))} href={item.href}>
            <Icon name={item.icon} />
            <span className="max-w-full truncate px-1">{item.label.split(" ")[0]}</span>
          </Link>
        ))}
        <button className={tab(moreActive)} type="button" onClick={() => setMoreOpen(true)}>
          <Icon name="more" />
          Ещё
        </button>
      </nav>
      <Drawer isOpen={moreOpen} placement="bottom" size="lg" onOpenChange={setMoreOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <DrawerHeader>Ещё</DrawerHeader>
              <DrawerBody className="gap-1 pb-8">
                {[...more, { section: "", href: "/profile", label: "Профиль", icon: "profile" }].map((item) => (
                  <Link
                    key={item.href}
                    className="flex items-center gap-3 rounded-lg px-3 py-3 hover:bg-default-100"
                    href={item.href}
                    onClick={close}
                  >
                    <Icon name={item.icon} />
                    {item.label}
                  </Link>
                ))}
                <button
                  className="flex items-center gap-3 rounded-lg px-3 py-3 text-left text-danger hover:bg-default-100"
                  type="button"
                  onClick={() => void logout()}
                >
                  <Icon name="logout" />
                  Выйти
                </button>
              </DrawerBody>
            </>
          )}
        </DrawerContent>
      </Drawer>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: me, isPending, isError, refetch } = useMe();

  if (isError && !me) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-4 text-center">
        <p className="text-default-600">Не удалось загрузить данные. Проверьте связь с сервером.</p>
        <Button color="primary" onPress={() => void refetch()}>
          Повторить
        </Button>
      </div>
    );
  }
  if (isPending || !me) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const items = visibleNav(me.permissions);
  const { main, more } = splitNav(items);

  return (
    <div className="min-h-dvh md:pl-64">
      <Sidebar items={items} pathname={pathname} />
      <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-divider bg-content1 px-4 py-2 md:px-8">
        <div className="rounded-md bg-sidebar px-3 py-2 md:hidden">
          <Logo tagline={false} className="[&>div]:text-xl" />
        </div>
        <div className="hidden text-sm text-default-500 md:block">
          {me.branch ? `Филиал: ${me.branch.name}` : "Все филиалы"}
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <div className="hidden md:block">
            <UserMenu me={me} />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 md:px-8 md:pb-10 md:pt-8">
        {canOpen(me.permissions, pathname) ? (
          children
        ) : (
          <p className="rounded-xl bg-content1 p-6 text-default-600">У вас нет доступа к этому разделу.</p>
        )}
      </main>
      <BottomNav main={main} more={more} pathname={pathname} />
    </div>
  );
}
