"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
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
import { activeHub, can, canOpen, hubsOf, splitNav, tabOf, visibleNav, type HubView } from "@/lib/permissions";
import type { Me } from "@/lib/types";
import { useOverlayMotion } from "@/lib/motion";

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

/** A hub shows the sum of its tabs' counters (e.g. reset requests on «Пользователи» -> «Настройки»). */
function hubBadge(hub: HubView, badges: Badges): number {
  return hub.tabs.reduce((sum, t) => sum + (badges[t.href] ?? 0), 0);
}

function Badge({ n }: { n: number | undefined }) {
  if (!n) return null;

  return (
    <span aria-label={`Новых запросов: ${n}`} className="sb-label ml-auto min-w-5 rounded-full bg-[#E26A3D] px-1.5 text-center text-xs font-semibold leading-5 text-[#0A0F14]">
      {n}
    </span>
  );
}

const ROW = "relative flex min-h-9 items-center gap-3 rounded-lg px-[15px] py-2 text-sm transition-colors";

function rowClass(active: boolean) {
  return `${ROW} w-full text-left ${active ? "sb-active bg-white/[0.07] font-medium text-white" : "text-[#aab5bf] hover:bg-white/5 hover:text-white"}`;
}

function HubIcon({ hub, active, badge }: { hub: HubView; active: boolean; badge: number }) {
  return (
    <span className={`relative shrink-0 ${active ? "text-[#38BDF0]" : ""}`}>
      <Icon name={hub.icon} size={18} />
      {/* collapsed rail: the count shows as a dot on the icon */}
      {badge ? <span className="sb-dot absolute -right-1.5 -top-1 hidden size-2.5 rounded-full bg-[#E26A3D]" /> : null}
    </span>
  );
}

/** Collapsed rail: the tabs of a hub in a small panel next to the rail. Esc, outside click or a pick closes it. */
function HubFlyout({ hub, pathname, badges, anchor, top, onClose }: { hub: HubView; pathname: string; badges: Badges; anchor: HTMLElement | null; top: number; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const current = tabOf(hub, pathname);

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("a")?.focus();

    const close = (focusBack: boolean) => {
      onClose();
      if (focusBack) anchor?.focus();
    };
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;

      if (!ref.current?.contains(target) && !anchor?.contains(target)) close(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(true);
    };

    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);

    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [anchor, onClose]);

  return (
    <div
      ref={ref}
      aria-label={hub.label}
      className="fixed left-[var(--sb-w)] z-40 ml-1 min-w-48 rounded-xl border border-divider bg-content1 p-1.5 text-sm shadow-lg"
      role="group"
      style={{ top }}
      onBlur={(e) => {
        if (!e.relatedTarget || ref.current?.contains(e.relatedTarget as Node) || anchor?.contains(e.relatedTarget as Node)) return;
        onClose();
      }}
    >
      <div className="px-2.5 pb-1 pt-1 text-[11px] font-medium uppercase tracking-[0.08em] text-default-500">{hub.label}</div>
      {hub.tabs.map((tab) => (
        <Link
          key={tab.href}
          aria-current={current === tab ? "page" : undefined}
          className={`flex min-h-9 items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-default-100 ${current === tab ? "font-medium text-brand-text" : ""}`}
          href={tab.href}
          onClick={onClose}
        >
          {tab.label}
          {badges[tab.href] ? <span className="ml-auto min-w-5 rounded-full bg-[#E26A3D] px-1.5 text-center text-xs font-semibold leading-5 text-[#0A0F14]">{badges[tab.href]}</span> : null}
        </Link>
      ))}
    </div>
  );
}

function HubRow({ hub, active, badges, collapsed, pathname }: { hub: HubView; active: boolean; badges: Badges; collapsed: boolean; pathname: string }) {
  const overlayMotion = useOverlayMotion();
  // the page the panel was opened on (and its top edge): another page closes it without an effect
  const [opened, setOpened] = useState<{ path: string; top: number } | null>(null);
  const open = opened?.path === pathname;
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const badge = hubBadge(hub, badges);
  const close = useCallback(() => setOpened(null), []);
  const content = (
    <>
      <HubIcon active={active} badge={badge} hub={hub} />
      <span className="sb-label">{hub.label}</span>
      <Badge n={badge} />
    </>
  );
  const flyout = collapsed && hub.tabs.length > 1;

  return (
    <Tooltip closeDelay={0} content={hub.label} delay={300} isDisabled={!collapsed || open} motionProps={overlayMotion} placement="right">
      {flyout ? (
        <div>
          <button
            ref={setAnchor}
            aria-controls={undefined}
            aria-current={active ? "page" : undefined}
            aria-expanded={open}
            aria-haspopup="true"
            aria-label={hub.label}
            className={rowClass(active)}
            type="button"
            onClick={(e) => setOpened(open ? null : { path: pathname, top: e.currentTarget.getBoundingClientRect().top })}
          >
            {content}
          </button>
          {open && <HubFlyout anchor={anchor} top={opened.top} badges={badges} hub={hub} pathname={pathname} onClose={close} />}
        </div>
      ) : (
        <Link aria-current={active ? "page" : undefined} className={rowClass(active)} href={hub.href}>
          {content}
        </Link>
      )}
    </Tooltip>
  );
}

function Sidebar({ hubs, current, pathname, badges }: { hubs: HubView[]; current: HubView | undefined; pathname: string; badges: Badges }) {
  const { collapsed, toggle } = useSidebarCollapsed();
  const overlayMotion = useOverlayMotion();
  const row = (hub: HubView) => (
    <HubRow key={hub.key} active={current === hub} badges={badges} collapsed={collapsed} hub={hub} pathname={pathname} />
  );
  const pinned = hubs.filter((h) => h.pinned);

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
      <nav aria-label="Разделы" className="flex flex-1 flex-col gap-0.5 overflow-y-auto overflow-x-hidden px-3 pb-3">
        {hubs.filter((h) => !h.pinned).map(row)}
        {pinned.length > 0 && (
          <div className="mt-auto flex flex-col gap-0.5 border-t border-white/[0.08] pt-2">{pinned.map(row)}</div>
        )}
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

/** Tabs of the hub the page belongs to: underline links, scroll sideways inside their own box on a phone. */
function HubTabs({ hub, pathname, badges }: { hub: HubView; pathname: string; badges: Badges }) {
  const current = tabOf(hub, pathname);

  return (
    <nav aria-label={hub.label} className="mb-5 overflow-x-auto border-b border-divider [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <ul className="flex w-max min-w-full gap-1">
        {hub.tabs.map((tab) => {
          const active = current === tab;

          return (
            <li key={tab.href} className="shrink-0">
              <Link
                aria-current={active ? "page" : undefined}
                className={`-mb-px flex min-h-11 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 text-sm transition-colors ${
                  active ? "border-brand-text font-medium text-brand-text" : "border-transparent text-default-500 hover:text-foreground"
                }`}
                href={tab.href}
              >
                {tab.label}
                {badges[tab.href] ? <span className="min-w-5 rounded-full bg-[#E26A3D] px-1.5 text-center text-xs font-semibold leading-5 text-[#0A0F14]">{badges[tab.href]}</span> : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
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

function BottomNav({ main, more, current, pathname, badges }: { main: HubView[]; more: HubView[]; current: HubView | undefined; pathname: string; badges: Badges }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const overlayMotion = useOverlayMotion();
  const logout = useLogout();
  const moreActive = (!!current && more.includes(current)) || pathname === "/profile";
  const tab = (active: boolean) =>
    `flex min-w-0 flex-1 flex-col items-center gap-0.5 py-2 text-[11px] ${active ? "text-brand-text" : "text-default-500"}`;

  return (
    <>
      <nav
        aria-label="Основное меню"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-[var(--hairline)] bg-content1/75 backdrop-blur-xl backdrop-saturate-150 pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] md:hidden"
      >
        {main.map((hub) => (
          <Link key={hub.key} aria-current={current === hub ? "page" : undefined} className={tab(current === hub)} href={hub.href}>
            <span className="relative">
              <Icon name={hub.icon} />
              {hubBadge(hub, badges) ? <span className="absolute -right-1.5 -top-1 size-2.5 rounded-full bg-[#E26A3D]" /> : null}
            </span>
            <span className="max-w-full truncate px-1">{hub.label}</span>
          </Link>
        ))}
        <button className={tab(moreActive)} type="button" onClick={() => setMoreOpen(true)}>
          <span className="relative">
            <Icon name="more" />
            {more.some((h) => hubBadge(h, badges)) ? <span className="absolute -right-1.5 -top-1 size-2.5 rounded-full bg-[#E26A3D]" /> : null}
          </span>
          Ещё
        </button>
      </nav>
      <Drawer isOpen={moreOpen} motionProps={overlayMotion} placement="bottom" size="lg" onOpenChange={setMoreOpen}>
        <DrawerContent>
          {(close) => (
            <>
              <SheetHandle onBackdrop={close} onClose={close} />
              <DrawerHeader>Ещё</DrawerHeader>
              <DrawerBody className="gap-1 pb-8">
                {[...more, { key: "profile", href: "/profile", label: "Профиль", icon: "profile", tabs: [] as HubView["tabs"] }].map((item) => (
                  <Link
                    key={item.key}
                    className="flex items-center gap-3 rounded-lg px-3 py-3 hover:bg-default-100"
                    href={item.href}
                    onClick={close}
                  >
                    <Icon name={item.icon} />
                    {item.label}
                    <Badge n={item.tabs.reduce((sum, t) => sum + (badges[t.href] ?? 0), 0)} />
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
        <header className="sticky top-0 z-20 h-[calc(57px+env(safe-area-inset-top))] border-b border-divider bg-content1" />
        <main className="mx-auto min-w-0 max-w-[88rem] pb-[calc(7rem+env(safe-area-inset-bottom))] pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-5 md:pb-10 md:pl-[max(2rem,env(safe-area-inset-left))] md:pr-[max(2rem,env(safe-area-inset-right))] md:pt-8">
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

  const hubs = hubsOf(visibleNav(me.permissions, me.role.code, me.teaches));
  const badges: Badges = { "/users": requests?.total ?? 0 };
  const { main, more } = splitNav(hubs, me.role.code);
  const here = activeHub(hubs, pathname);
  const allowed = canOpen(me.permissions, pathname, me.role.code, me.teaches);

  return (
    <div className="sb-shell min-h-dvh">
      <TopProgress />
      <Sidebar badges={badges} current={here?.hub} hubs={hubs} pathname={pathname} />
      <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-[var(--hairline)] bg-content1/70 backdrop-blur-xl backdrop-saturate-150 pb-2 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-[calc(0.5rem+env(safe-area-inset-top))] md:pl-[max(2rem,env(safe-area-inset-left))] md:pr-[max(2rem,env(safe-area-inset-right))]">
        <Logo tagline={false} className="md:hidden [&>div]:text-xl" tone="text-brand-text dark:text-white" />
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
      <main className="mx-auto min-w-0 max-w-[88rem] pb-[calc(7rem+env(safe-area-inset-bottom))] pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pt-5 md:pb-10 md:pl-[max(2rem,env(safe-area-inset-left))] md:pr-[max(2rem,env(safe-area-inset-right))] md:pt-8">
        {allowed && here && here.hub.tabs.length > 1 && <HubTabs badges={badges} hub={here.hub} pathname={pathname} />}
        {allowed ? (
          <div key={pathname} className="page-in">
            {children}
          </div>
        ) : (
          <p className="rounded-xl bg-content1 p-6 text-default-600">У вас нет доступа к этому разделу.</p>
        )}
      </main>
      <BottomNav badges={badges} current={here?.hub} main={main} more={more} pathname={pathname} />
    </div>
  );
}
