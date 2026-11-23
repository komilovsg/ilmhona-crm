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

export type NavGroup = "main" | "sales" | "study" | "money" | "admin";

/** The sidebar sections, top to bottom. «main» has no heading. */
export const NAV_GROUPS: { key: NavGroup; label: string }[] = [
  { key: "main", label: "" },
  { key: "sales", label: "Продажи" },
  { key: "study", label: "Обучение" },
  { key: "money", label: "Финансы" },
  { key: "admin", label: "Управление" },
];

export type NavItem = {
  /** Backend section key that must be at least `view`. */
  section: string;
  href: string;
  label: string;
  icon: string;
  /** Where the item sits in the desktop sidebar (`NAV_GROUPS`). */
  group: NavGroup;
  /** `own`: only for users who teach (any role); `staff`: only for everybody but the instructor role; default: all. */
  audience?: "own" | "staff";
};

// Order = order in the sidebar. `section` keys are the backend's (app/permissions.py).
export const NAV_ITEMS: NavItem[] = [
  { section: "dashboard", group: "main", href: "/dashboard", label: "Дашборд", icon: "dashboard", audience: "staff" },
  // the instructor's home (a manager with the attendance right sees it too): today's lessons, «не заполнено»
  { section: "attendance", group: "main", href: "/today", label: "Сегодня", icon: "attendance" },
  { section: "leads", group: "sales", href: "/leads", label: "Лиды", icon: "leads" },
  { section: "students", group: "study", href: "/students", label: "Студенты", icon: "students" },
  { section: "cohorts", group: "study", href: "/cohorts", label: "Потоки", icon: "cohorts" },
  { section: "payments", group: "money", href: "/payments", label: "Оплаты", icon: "payments" },
  { section: "rooms", group: "study", href: "/rooms", label: "Расписание", icon: "rooms" },
  { section: "graduates", group: "study", href: "/graduates", label: "Выпускники и трудоустройство", icon: "graduates", audience: "staff" },
  { section: "certificates", group: "study", href: "/certificates", label: "Сертификаты", icon: "certificate", audience: "staff" },
  { section: "master_list", group: "money", href: "/master-list", label: "Мастер-лист", icon: "master", audience: "staff" },
  { section: "marketing", group: "sales", href: "/marketing", label: "Маркетинг", icon: "marketing" },
  // the instructor sees only their own money: one page instead of the instructors and salaries tables
  { section: "instructors", group: "money", href: "/my-payouts", label: "Мои выплаты", icon: "payments", audience: "own" },
  { section: "instructors", group: "study", href: "/instructors", label: "Инструкторы", icon: "instructors", audience: "staff" },
  { section: "instructors", group: "money", href: "/salaries", label: "Зарплаты", icon: "payments", audience: "staff" },
  { section: "users", group: "admin", href: "/users", label: "Пользователи", icon: "users" },
  { section: "users", group: "admin", href: "/roles", label: "Роли и права", icon: "roles" },
  { section: "audit", group: "admin", href: "/audit", label: "Журнал", icon: "audit" },
  // «Настройки → Стандарты академии»: staff who grade read it, the superadmin changes it (an
  // instructor sees the scheme of their cohort on the cohort page)
  { section: "cert_templates", group: "study", href: "/settings/certificates", label: "Сертификаты", icon: "certificate" },
  { section: "attendance", group: "admin", href: "/settings/grading", label: "Стандарты академии", icon: "sliders", audience: "staff" },
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

  return can(permissions, item.section, "view") && forRole(item, roleCode, teaches);
}

/** The sidebar: only sections the user may at least view (and pages meant for their role). */
export function visibleNav(permissions: Permissions | undefined, roleCode?: string | null, teaches?: boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => shown(item, permissions, roleCode, teaches));
}

export const BOTTOM_NAV_SIZE = 4;

const MONEY_NAV = ["/dashboard", "/leads", "/students", "/payments"];

/**
 * Phone: four visible items go to the bottom bar, the rest to the «Ещё» sheet. A user who sees payments
 * (not an instructor) gets Дашборд · Лиды · Студенты · Оплаты; «Сегодня» moves to «Ещё». Others: the first four.
 */
export function splitNav(items: NavItem[], roleCode?: string | null): { main: NavItem[]; more: NavItem[] } {
  const money = roleCode !== "instructor" && items.some((i) => i.href === "/payments");
  const main = money ? MONEY_NAV.flatMap((href) => items.filter((i) => i.href === href)) : [];

  for (const item of items) if (main.length < BOTTOM_NAV_SIZE && !main.includes(item)) main.push(item);

  return { main: items.filter((i) => main.includes(i)), more: items.filter((i) => !main.includes(i)) };
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
