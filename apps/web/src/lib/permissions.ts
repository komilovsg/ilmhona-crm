// Pure rights and navigation logic (no React, no imports: unit-tested with node --test).

export type Level = "view" | "change";
export type Permissions = Record<string, Level | undefined>;

const RANK: Record<string, number> = { view: 1, change: 2 };

/** `change` includes `view` (and delete): has `have` at least `need`? */
export function allows(have: string | undefined, need: Level): boolean {
  return (RANK[have ?? ""] ?? 0) >= RANK[need];
}

export function can(
  permissions: Permissions | undefined,
  section: string,
  need: Level = "view",
): boolean {
  return allows(permissions?.[section], need);
}

export type HubKey = "dashboard" | "today" | "sales" | "study" | "finance" | "settings";

export type Hub = {
  key: HubKey;
  label: string;
  icon: string;
  /** Pinned at the bottom of the sidebar, after a divider. */
  pinned?: boolean;
};

/** The sidebar sections (hubs), top to bottom. Each hub holds the pages that show as its tabs. */
export const HUBS: Hub[] = [
  { key: "dashboard", label: "Дашборд", icon: "dashboard" },
  { key: "today", label: "Сегодня", icon: "attendance" },
  { key: "sales", label: "Продажи", icon: "trending-up" },
  { key: "study", label: "Обучение", icon: "students" },
  { key: "finance", label: "Финансы", icon: "wallet" },
  { key: "settings", label: "Настройки", icon: "settings", pinned: true },
];

export type NavItem = {
  /** Backend section key that must be at least `view`. */
  section: string;
  /** A second section whose view right shows the item too (one menu item for two sections). */
  alsoSection?: string;
  href: string;
  label: string;
  icon: string;
  /** The hub this page is a tab of. */
  hub: HubKey;
  /** `own`: only for users who teach (any role); `staff`: only for everybody but the instructor role; default: all. */
  audience?: "own" | "staff";
};

// Order = order of the tabs inside a hub. `section` keys are the backend's (app/permissions.py).
export const NAV_ITEMS: NavItem[] = [
  { section: "dashboard", hub: "dashboard", href: "/dashboard", label: "Дашборд", icon: "dashboard", audience: "staff" },
  // the instructor's home (a manager with the attendance right sees it too): today's lessons, «не заполнено»
  { section: "attendance", hub: "today", href: "/today", label: "Сегодня", icon: "attendance" },
  { section: "leads", hub: "sales", href: "/leads", label: "Лиды", icon: "leads" },
  { section: "marketing", hub: "sales", href: "/marketing", label: "Маркетинг", icon: "marketing" },
  { section: "students", hub: "study", href: "/students", label: "Студенты", icon: "students" },
  { section: "cohorts", hub: "study", href: "/cohorts", label: "Потоки", icon: "cohorts" },
  { section: "rooms", hub: "study", href: "/rooms", label: "Расписание", icon: "rooms" },
  { section: "instructors", hub: "study", href: "/instructors", label: "Инструкторы", icon: "instructors", audience: "staff" },
  { section: "graduates", hub: "study", href: "/graduates", label: "Выпускники", icon: "graduates", audience: "staff" },
  // one item for the registry and the templates (tabs inside); templates alone also open it
  { section: "certificates", alsoSection: "cert_templates", hub: "study", href: "/certificates", label: "Сертификаты", icon: "certificate", audience: "staff" },
  { section: "payments", hub: "finance", href: "/payments", label: "Оплаты", icon: "payments" },
  { section: "master_list", hub: "finance", href: "/master-list", label: "Мастер-лист", icon: "master", audience: "staff" },
  { section: "instructors", hub: "finance", href: "/salaries", label: "Зарплаты", icon: "payments", audience: "staff" },
  // the instructor sees only their own money: one page instead of the instructors and salaries tables
  { section: "instructors", hub: "finance", href: "/my-payouts", label: "Мои выплаты", icon: "payments", audience: "own" },
  { section: "users", hub: "settings", href: "/users", label: "Пользователи", icon: "users" },
  { section: "users", hub: "settings", href: "/roles", label: "Роли и права", icon: "roles" },
  { section: "audit", hub: "settings", href: "/audit", label: "Журнал", icon: "audit" },
  // «Настройки → Стандарты академии»: staff who grade read it, the superadmin changes it (an
  // instructor sees the scheme of their cohort on the cohort page)
  { section: "attendance", hub: "settings", href: "/settings/grading", label: "Стандарты академии", icon: "sliders", audience: "staff" },
  { section: "donors", hub: "settings", href: "/settings/donors", label: "Доноры", icon: "cross", audience: "staff" },
];

function forRole(item: NavItem, roleCode: string | null | undefined, teaches?: boolean): boolean {
  if (!item.audience) return true;
  // «Мои выплаты» follows the «Ведёт занятия» flag, whatever the role
  if (item.audience === "own") return !!teaches;

  return roleCode !== "instructor";
}

/** Own pages need no section right: the API lets a teaching user read their own card and money. */
function shown(item: NavItem, permissions: Permissions | undefined, roleCode: string | null | undefined, teaches?: boolean): boolean {
  if (item.audience === "own") return !!teaches;

  const seen = can(permissions, item.section, "view") || (!!item.alsoSection && can(permissions, item.alsoSection, "view"));

  return seen && forRole(item, roleCode, teaches);
}

/** The sidebar: only sections the user may at least view (and pages meant for their role). */
export function visibleNav(permissions: Permissions | undefined, roleCode?: string | null, teaches?: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => shown(item, permissions, roleCode, teaches));
}

/** A hub the user can open: its visible tabs (never empty). One tab = a plain link, no tab bar. */
export type HubView = Hub & {
  tabs: NavItem[];
  /** The first visible tab: where a click on the hub goes. */
  href: string;
};

/** Hubs with at least one visible tab, in sidebar order. */
export function hubsOf(items: NavItem[]): HubView[] {
  return HUBS.flatMap((hub) => {
    const tabs = items.filter((i) => i.hub === hub.key);

    return tabs.length > 0 ? [{ ...hub, tabs, href: tabs[0].href }] : [];
  });
}

export function visibleHubs(permissions: Permissions | undefined, roleCode?: string | null, teaches?: boolean): HubView[] {
  return hubsOf(visibleNav(permissions, roleCode, teaches));
}

/** Pages that are not a tab themselves but belong to one. */
const TAB_ALIASES: [prefix: string, href: string][] = [
  ["/employment", "/graduates"],
  ["/settings/certificates", "/certificates"],
];

function tabPath(pathname: string): string {
  const alias = TAB_ALIASES.find(([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  return alias ? alias[1] : pathname;
}

/** The tab of `hub` that holds `pathname` (detail pages included), if any. */
export function tabOf(hub: HubView, pathname: string): NavItem | undefined {
  const path = tabPath(pathname);

  return hub.tabs
    .filter((t) => path === t.href || path.startsWith(`${t.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];
}

/** The hub (and its tab) that holds the current page. */
export function activeHub(hubs: HubView[], pathname: string): { hub: HubView; tab: NavItem } | undefined {
  for (const hub of hubs) {
    const tab = tabOf(hub, pathname);

    if (tab) return { hub, tab };
  }

  return undefined;
}

export const BOTTOM_NAV_SIZE = 4;

const MONEY_HUBS: HubKey[] = ["dashboard", "sales", "study", "finance"];

/**
 * Phone: four hubs go to the bottom bar, the rest to the «Ещё» sheet. A user who sees finance
 * (not an instructor) gets Дашборд · Продажи · Обучение · Финансы; «Сегодня» and «Настройки» go to «Ещё».
 * Others: the first four.
 */
export function splitNav(hubs: HubView[], roleCode?: string | null): { main: HubView[]; more: HubView[] } {
  const money = roleCode !== "instructor" && hubs.some((h) => h.key === "finance");
  const main = money ? hubs.filter((h) => MONEY_HUBS.includes(h.key)) : [];

  for (const hub of hubs) if (main.length < BOTTOM_NAV_SIZE && !main.includes(hub)) main.push(hub);

  return { main: hubs.filter((h) => main.includes(h)), more: hubs.filter((h) => !main.includes(h)) };
}

/** Where to land after sign-in: the dashboard, else the first allowed section, else the profile. */
export function homePath(permissions: Permissions | undefined, roleCode?: string | null, teaches?: boolean): string {
  return visibleNav(permissions, roleCode, teaches)[0]?.href ?? "/profile";
}

/** May this user open `pathname`? Profile is always open; unknown paths are left to 404. */
export function canOpen(permissions: Permissions | undefined, pathname: string, roleCode?: string | null, teaches?: boolean): boolean {
  if (pathname === "/profile") return true;
  // the employment list is a page of «Выпускники и трудоустройство»
  const path = pathname === "/employment" ? "/graduates" : pathname;
  // the template editor lives under settings but is part of «Сертификаты»
  if (path === "/settings/certificates" || path.startsWith("/settings/certificates/")) {
    return can(permissions, "cert_templates", "view") && roleCode !== "instructor";
  }
  const item = NAV_ITEMS.find((i) => path === i.href || path.startsWith(`${i.href}/`));

  return item ? shown(item, permissions, roleCode, teaches) : true;
}

// Matrix editor: three columns, «change» implies delete (no separate column).
export type MatrixChoice = "none" | Level;

export function toMatrix(permissions: Permissions, sections: string[]): Record<string, MatrixChoice> {
  return Object.fromEntries(sections.map((s) => [s, permissions[s] ?? "none"]));
}

export function fromMatrix(matrix: Record<string, MatrixChoice>): Record<string, Level> {
  return Object.fromEntries(
    Object.entries(matrix).filter((entry): entry is [string, Level] => entry[1] !== "none"),
  );
}
