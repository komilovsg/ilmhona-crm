"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@heroui/button";
import { Drawer, DrawerBody, DrawerContent, DrawerHeader } from "@heroui/drawer";
import { SheetHandle } from "./SheetHandle";
import { Tooltip } from "@heroui/tooltip";
import { Dropdown, DropdownItem, DropdownMenu, DropdownTrigger } from "@heroui/dropdown";

import { IlmMark } from "./brand/IlmMark";
import { Icon } from "./Icon";
import { Logo } from "./Logo";
import { ErrorState } from "./QueryState";
import { HeaderSkeleton, Late, ListSkeleton } from "./Skeletons";
import { ThemeToggle } from "./ThemeToggle";
import { TopProgress } from "./TopProgress";

import { useMe, useResetRequests } from "@/hooks/queries";
import { SIDEBAR_STORAGE_KEY } from "@/context/theme-init";
import { api } from "@/lib/api";
import { useBrowserValue } from "@/lib/client-store";
import { can, canOpen, splitNav, visibleNav, type NavItem } from "@/lib/permissions";
import type { Me } from "@/lib/types";
import { useOverlayMotion } from "@/lib/motion";

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

const SIDEBAR_EVENT = "ilm-sidebar-change";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "collapsed";
  } catch {
    return false;
  }
}

/**
 * Collapsed state. The layout itself reads `html[data-sidebar]` (set before the first paint), so React only
 * needs the flag for the toggle's label and the tooltips; it is `false` until hydrated.
 */
function useSidebarCollapsed() {
  const collapsed = useBrowserValue(readCollapsed, false, SIDEBAR_EVENT);
  const toggle = useCallback(() => {
    const next = !readCollapsed();

    try {
      if (next) localStorage.setItem(SIDEBAR_STORAGE_KEY, "collapsed");
      else localStorage.removeItem(SIDEBAR_STORAGE_KEY);
    } catch {
      // not remembered, still works for this visit
    }
    if (next) document.documentElement.dataset.sidebar = "collapsed";
    else delete document.documentElement.dataset.sidebar;
    window.dispatchEvent(new Event(SIDEBAR_EVENT));
  }, []);

  // «[» toggles, like in Linear / Notion; never while typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;

      if (e.key !== "[" || e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      if (el?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) return;
      toggle();
    };

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  return { collapsed, toggle };
}

type Badges = Record<string, number>;

function Badge({ n }: { n: number | undefined }) {
  if (!n) return null;

  return (
    <span aria-label={`Новых запросов: ${n}`} className="sb-label ml-auto min-w-5 rounded-full bg-[#E26A3D] px-1.5 text-center text-xs font-semibold leading-5 text-[#0A0F14]">
      {n}
    </span>
  );
}

const ROW = "relative flex items-center gap-3 rounded-lg px-[15px] py-2.5 text-sm transition-colors";

function Sidebar({ items, pathname, badges }: { items: NavItem[]; pathname: string; badges: Badges }) {
  const { collapsed, toggle } = useSidebarCollapsed();
  const overlayMotion = useOverlayMotion();

  return (
    <aside className="sb-aside fixed inset-y-0 left-0 hidden flex-col bg-sidebar md:flex">
      <div className="py-6 pl-[19px]">
        <Link aria-label="ilmhona" className="flex items-center gap-3 text-white" href="/">
          <IlmMark className="shrink-0" height={27} />
          <span className="sb-label leading-none">
            <span className="block text-2xl font-bold tracking-tight">ilmhona</span>
            <span className="mt-1 block text-[11px] tracking-wide text-[#8B98A5]">skills accelerator</span>
          </span>
        </Link>
      </div>
      <nav aria-label="Разделы" className="flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden px-3 pb-3">
        {items.map((item) => {
          const active = isActive(pathname, item.href);
          const badge = badges[item.href];

          return (
            <Tooltip
              key={item.href}
              closeDelay={0}
              content={item.label}
              delay={300}
              isDisabled={!collapsed}
              motionProps={overlayMotion}
              placement="right"
            >
              <Link
                aria-current={active ? "page" : undefined}
                className={`${ROW} ${
                  active ? "bg-[#00A0DC]/15 text-[#38BDF0]" : "text-[#aab5bf] hover:bg-white/5 hover:text-white"
                }`}
                href={item.href}
              >
                <span className="relative shrink-0">
                  <Icon name={item.icon} size={18} />
                  {/* collapsed rail: the count shows as a dot on the icon */}
                  {badge ? <span className="sb-dot absolute -right-1.5 -top-1 hidden size-2.5 rounded-full bg-[#E26A3D]" /> : null}
                </span>
                <span className="sb-label">{item.label}</span>
                <Badge n={badge} />
              </Link>
            </Tooltip>
          );
        })}
      </nav>
      <div className="px-3 pb-4">
        <Tooltip closeDelay={0} content="Развернуть  [" delay={300} isDisabled={!collapsed} motionProps={overlayMotion} placement="right">
          <button
            aria-expanded={!collapsed}
            aria-keyshortcuts="["
            aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
            className={`${ROW} w-full text-left text-[#8B98A5] hover:bg-white/5 hover:text-white`}
            type="button"
            onClick={toggle}
          >
            <Icon className="shrink-0" name="sidebar" size={18} />
            <span className="sb-label flex-1">Свернуть</span>
            <kbd className="sb-label rounded border border-white/15 px-1.5 text-[11px] text-[#8B98A5]">[</kbd>
          </button>
        </Tooltip>
      </div>
    </aside>
  );
}

function UserMenu({ me }: { me: Me }) {
  const logout = useLogout();
  const router = useRouter();
  const overlayMotion = useOverlayMotion();

  return (
    <Dropdown motionProps={overlayMotion} placement="bottom-end">
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

function BottomNav({ main, more, pathname, badges }: { main: NavItem[]; more: NavItem[]; pathname: string; badges: Badges }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const overlayMotion = useOverlayMotion();
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
            <span className="relative">
              <Icon name={item.icon} />
              {badges[item.href] ? <span className="absolute -right-1.5 -top-1 size-2.5 rounded-full bg-[#E26A3D]" /> : null}
            </span>
            <span className="max-w-full truncate px-1">{item.label.split(" ")[0]}</span>
          </Link>
        ))}
        <button className={tab(moreActive)} type="button" onClick={() => setMoreOpen(true)}>
          <span className="relative">
            <Icon name="more" />
            {more.some((i) => badges[i.href]) ? <span className="absolute -right-1.5 -top-1 size-2.5 rounded-full bg-[#E26A3D]" /> : null}
          </span>
          Ещё
        </button>
      </nav>
      <Drawer isOpen={moreOpen} motionProps={overlayMotion} placement="bottom" size="lg" onOpenChange={setMoreOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <SheetHandle onClose={close} />
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
                    <Badge n={badges[item.href]} />
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
  const { data: requests } = useResetRequests(!!me && !me.must_change_password && can(me.permissions, "users", "change"));

  if (isError && !me) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4">
        <ErrorState onRetry={() => void refetch()} />
      </div>
    );
  }
  if (isPending || !me) {
    // the frame of the real shell, so the page does not jump when the user arrives
    return (
      <div aria-busy="true" className="sb-shell min-h-dvh">
        <TopProgress />
        <aside className="sb-aside fixed inset-y-0 left-0 hidden bg-sidebar md:block" />
        <header className="sticky top-0 z-20 h-[57px] border-b border-divider bg-content1" />
        <main className="mx-auto max-w-6xl px-4 pb-28 pt-5 md:px-8 md:pb-10 md:pt-8">
          <span className="sr-only" role="status">
            Загрузка…
          </span>
          <Late>
            <HeaderSkeleton />
            <ListSkeleton />
          </Late>
        </main>
      </div>
    );
  }

  const items = visibleNav(me.permissions, me.role.code);
  const badges: Badges = { "/users": requests?.total ?? 0 };
  const { main, more } = splitNav(items);

  return (
    <div className="sb-shell min-h-dvh">
      <TopProgress />
      <Sidebar badges={badges} items={items} pathname={pathname} />
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
        {canOpen(me.permissions, pathname, me.role.code) ? (
          <div key={pathname} className="page-in">
            {children}
          </div>
        ) : (
          <p className="rounded-xl bg-content1 p-6 text-default-600">У вас нет доступа к этому разделу.</p>
        )}
      </main>
      <BottomNav badges={badges} main={main} more={more} pathname={pathname} />
    </div>
  );
}
