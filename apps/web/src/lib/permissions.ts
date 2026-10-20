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
};

// Order = order in the sidebar. `section` keys are the backend's (app/permissions.py).
export const NAV_ITEMS: NavItem[] = [
  { section: "dashboard", href: "/dashboard", label: "Дашборд", icon: "dashboard" },
  { section: "leads", href: "/leads", label: "Лиды", icon: "leads" },
  { section: "students", href: "/students", label: "Студенты", icon: "students" },
  { section: "cohorts", href: "/cohorts", label: "Потоки", icon: "cohorts" },
  { section: "attendance", href: "/attendance", label: "Посещаемость и оценки", icon: "attendance" },
  { section: "payments", href: "/payments", label: "Оплаты", icon: "payments" },
  { section: "rooms", href: "/rooms", label: "Аудитории", icon: "rooms" },
  { section: "graduates", href: "/graduates", label: "Выпускники и трудоустройство", icon: "graduates" },
  { section: "master_list", href: "/master-list", label: "Мастер-лист", icon: "master" },
  { section: "marketing", href: "/marketing", label: "Маркетинг", icon: "marketing" },
  { section: "instructors", href: "/instructors", label: "Инструкторы и зарплаты", icon: "instructors" },
  { section: "users", href: "/users", label: "Пользователи", icon: "users" },
  { section: "users", href: "/roles", label: "Роли и права", icon: "roles" },
  { section: "audit", href: "/audit", label: "Журнал", icon: "audit" },
];

/** The sidebar: only sections the user may at least view. */
export function visibleNav(permissions: Permissions | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => can(permissions, item.section, "view"));
}

export const BOTTOM_NAV_SIZE = 4;

/** Phone: the first four visible items go to the bottom bar, the rest to the «Ещё» sheet. */
export function splitNav(items: NavItem[]): { main: NavItem[]; more: NavItem[] } {
  return { main: items.slice(0, BOTTOM_NAV_SIZE), more: items.slice(BOTTOM_NAV_SIZE) };
}

/** Where to land after sign-in: the dashboard, else the first allowed section, else the profile. */
export function homePath(permissions: Permissions | undefined): string {
  return visibleNav(permissions)[0]?.href ?? "/profile";
}

/** May this user open `pathname`? Profile is always open; unknown paths are left to 404. */
export function canOpen(permissions: Permissions | undefined, pathname: string): boolean {
  if (pathname === "/profile") return true;
  const item = NAV_ITEMS.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));

  return item ? can(permissions, item.section, "view") : true;
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
