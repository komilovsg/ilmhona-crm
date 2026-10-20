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

export type NavItem = {
  /** Backend section key that must be at least `view`. */
  section: string;
  href: string;
  label: string;
  icon: string;
  /** Only for the instructor role (`own`) or only for everybody else (`staff`); default: all. */
  audience?: "own" | "staff";
};

// Order = order in the sidebar. `section` keys are the backend's (app/permissions.py).
export const NAV_ITEMS: NavItem[] = [
  { section: "dashboard", href: "/dashboard", label: "Дашборд", icon: "dashboard" },
  // the instructor's home (a manager with the attendance right sees it too): today's lessons, «не заполнено»
  { section: "attendance", href: "/today", label: "Сегодня", icon: "attendance" },
  { section: "leads", href: "/leads", label: "Лиды", icon: "leads" },
  { section: "students", href: "/students", label: "Студенты", icon: "students" },
  { section: "cohorts", href: "/cohorts", label: "Потоки", icon: "cohorts" },
  { section: "payments", href: "/payments", label: "Оплаты", icon: "payments" },
  { section: "rooms", href: "/rooms", label: "Аудитории", icon: "rooms" },
  { section: "graduates", href: "/graduates", label: "Выпускники и трудоустройство", icon: "graduates" },
  { section: "master_list", href: "/master-list", label: "Мастер-лист", icon: "master" },
  { section: "marketing", href: "/marketing", label: "Маркетинг", icon: "marketing" },
  // the instructor sees only their own money: one page instead of the instructors and salaries tables
  { section: "instructors", href: "/my-payouts", label: "Мои выплаты", icon: "payments", audience: "own" },
  { section: "instructors", href: "/instructors", label: "Инструкторы", icon: "instructors", audience: "staff" },
  { section: "instructors", href: "/salaries", label: "Зарплаты", icon: "payments", audience: "staff" },
  { section: "users", href: "/users", label: "Пользователи", icon: "users" },
  { section: "users", href: "/roles", label: "Роли и права", icon: "roles" },
  { section: "audit", href: "/audit", label: "Журнал", icon: "audit" },
];

function forRole(item: NavItem, roleCode: string | null | undefined): boolean {
  if (!item.audience) return true;

  return (item.audience === "own") === (roleCode === "instructor");
}

/** The sidebar: only sections the user may at least view (and pages meant for their role). */
export function visibleNav(permissions: Permissions | undefined, roleCode?: string | null): NavItem[] {
  return NAV_ITEMS.filter((item) => can(permissions, item.section, "view") && forRole(item, roleCode));
}

export const BOTTOM_NAV_SIZE = 4;

/** Phone: the first four visible items go to the bottom bar, the rest to the «Ещё» sheet. */
export function splitNav(items: NavItem[]): { main: NavItem[]; more: NavItem[] } {
  return { main: items.slice(0, BOTTOM_NAV_SIZE), more: items.slice(BOTTOM_NAV_SIZE) };
}

/** Where to land after sign-in: the dashboard, else the first allowed section, else the profile. */
export function homePath(permissions: Permissions | undefined, roleCode?: string | null): string {
  return visibleNav(permissions, roleCode)[0]?.href ?? "/profile";
}

/** May this user open `pathname`? Profile is always open; unknown paths are left to 404. */
export function canOpen(permissions: Permissions | undefined, pathname: string, roleCode?: string | null): boolean {
  if (pathname === "/profile") return true;
  const item = NAV_ITEMS.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));

  return item ? can(permissions, item.section, "view") && forRole(item, roleCode) : true;
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
