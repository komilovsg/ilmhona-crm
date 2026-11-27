import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allows,
  canOpen,
  fromMatrix,
  homePath,
  activeHub,
  NAV_ITEMS,
  splitNav,
  tabOf,
  toMatrix,
  visibleHubs,
  visibleNav,
  type MatrixChoice,
  type Permissions,
} from "./permissions.ts";

const manager: Permissions = {
  dashboard: "view",
  leads: "change",
  students: "change",
  cohorts: "change",
  payments: "change",
  rooms: "change",
};
const instructor: Permissions = { cohorts: "view", attendance: "change", instructors: "view" };

test("change includes view, view does not include change", () => {
  assert.equal(allows("change", "view"), true);
  assert.equal(allows("view", "change"), false);
  assert.equal(allows(undefined, "view"), false);
});

test("nav shows only sections with at least view", () => {
  assert.deepEqual(
    visibleNav(instructor, "instructor", true).map((i) => i.section),
    ["attendance", "cohorts", "instructors"],
  );
  assert.deepEqual(visibleNav(undefined), []);
  assert.equal(visibleNav(manager).some((i) => i.section === "users"), false);
});

test("the instructor gets «Мои выплаты» only; staff get «Инструкторы» and «Зарплаты»", () => {
  assert.deepEqual(
    visibleNav(instructor, "instructor", true).map((i) => i.href),
    ["/today", "/cohorts", "/my-payouts"],
  );
  assert.deepEqual(
    visibleNav({ instructors: "view" }, "manager").map((i) => i.href),
    ["/instructors", "/salaries"],
  );
  assert.equal(canOpen(instructor, "/salaries", "instructor"), false);
  assert.equal(canOpen(instructor, "/instructors", "instructor"), false);
  assert.equal(canOpen(instructor, "/my-payouts", "instructor", true), true);
  assert.equal(canOpen({ instructors: "view" }, "/my-payouts", "manager"), false);
});

test("«Мои выплаты» follows the teaches flag, not the role", () => {
  // a teaching superadmin / manager: own page plus the staff pages
  const boss = Object.fromEntries(NAV_ITEMS.map((i) => [i.section, "change"])) as Permissions;
  assert.ok(visibleNav(boss, "superadmin", true).some((i) => i.href === "/my-payouts"));
  assert.ok(visibleNav(boss, "superadmin", true).some((i) => i.href === "/instructors"));
  assert.equal(visibleNav(boss, "superadmin", false).some((i) => i.href === "/my-payouts"), false);
  // no instructors right needed for the own page
  assert.deepEqual(visibleNav({ cohorts: "view" }, "manager", true).map((i) => i.href), ["/cohorts", "/my-payouts"]);
  assert.equal(canOpen({ cohorts: "view" }, "/my-payouts", "manager", true), true);
  assert.equal(canOpen({ instructors: "view" }, "/my-payouts", "manager", false), false);
  // an instructor role whose flag was switched off has no own page
  assert.equal(visibleNav(instructor, "instructor", false).some((i) => i.href === "/my-payouts"), false);
});

test("users section opens both Пользователи and Роли, audit is separate", () => {
  const nav = visibleNav({ users: "view" }).map((i) => i.href);
  assert.deepEqual(nav, ["/users", "/roles"]);
  assert.deepEqual(visibleNav({ audit: "view" }).map((i) => i.href), ["/audit"]);
});

test("every backend section has a nav item", () => {
  const sections = new Set(NAV_ITEMS.flatMap((i) => [i.section, ...(i.alsoSection ? [i.alsoSection] : [])]));
  assert.equal(sections.size, 16);
});

const everything = Object.fromEntries(NAV_ITEMS.flatMap((i) => [[i.section, "change"], ...(i.alsoSection ? [[i.alsoSection, "change"]] : [])])) as Permissions;
const hubTabs = (p: Permissions, role: string, teaches?: boolean) =>
  Object.fromEntries(visibleHubs(p, role, teaches).map((h) => [h.key, h.tabs.map((t) => t.href)]));

test("hubs per role: instructor", () => {
  const hubs = visibleHubs(instructor, "instructor", true);
  assert.deepEqual(hubs.map((h) => h.key), ["today", "study", "finance"]);
  // the instructor sees one tab in «Обучение» and «Финансы»: plain links, no tab bar
  assert.deepEqual(hubs.map((h) => h.tabs.length), [1, 1, 1]);
  assert.deepEqual(hubs.map((h) => h.href), ["/today", "/cohorts", "/my-payouts"]);
});

test("hubs per role: manager", () => {
  const withToday = { ...manager, attendance: "view" } as Permissions;
  assert.deepEqual(hubTabs(withToday, "manager"), {
    dashboard: ["/dashboard"],
    today: ["/today"],
    sales: ["/leads"],
    study: ["/students", "/cohorts", "/rooms"],
    finance: ["/payments"],
    settings: ["/settings/grading"],
  });
  // a hub without a visible tab is gone
  assert.equal(visibleHubs(manager, "manager").some((h) => h.key === "settings"), false);
});

test("hubs per role: superadmin sees every hub with all its tabs; settings is pinned", () => {
  const hubs = visibleHubs(everything, "superadmin", true);
  assert.deepEqual(hubs.map((h) => h.key), ["dashboard", "today", "sales", "study", "finance", "settings"]);
  assert.deepEqual(hubs.find((h) => h.key === "study")?.tabs.map((t) => t.label), ["Студенты", "Потоки", "Расписание", "Инструкторы", "Выпускники", "Сертификаты"]);
  assert.deepEqual(hubs.find((h) => h.key === "finance")?.tabs.map((t) => t.label), ["Оплаты", "Мастер-лист", "Зарплаты", "Мои выплаты"]);
  assert.deepEqual(hubs.find((h) => h.key === "settings")?.tabs.map((t) => t.href), ["/users", "/roles", "/audit", "/settings/grading", "/settings/donors"]);
  assert.deepEqual(hubs.filter((h) => h.pinned).map((h) => h.key), ["settings"]);
  // a click on a hub goes to its first visible tab
  assert.equal(hubs.find((h) => h.key === "sales")?.href, "/leads");
  assert.equal(visibleHubs({ audit: "view" }, "manager")[0].href, "/audit");
});

test("a hub with one visible tab acts as a link to that tab", () => {
  const [hub] = visibleHubs({ marketing: "view" }, "manager");
  assert.equal(hub.key, "sales");
  assert.equal(hub.tabs.length, 1);
  assert.equal(hub.href, "/marketing");
});

test("active hub holds detail pages and aliases", () => {
  const hubs = visibleHubs(everything, "superadmin", true);
  const at = (path: string) => {
    const found = activeHub(hubs, path);
    return found && [found.hub.key, found.tab.href];
  };
  assert.deepEqual(at("/students/123"), ["study", "/students"]);
  assert.deepEqual(at("/cohorts/x"), ["study", "/cohorts"]);
  assert.deepEqual(at("/certificates"), ["study", "/certificates"]);
  assert.deepEqual(at("/settings/certificates/abc"), ["study", "/certificates"]);
  assert.deepEqual(at("/employment"), ["study", "/graduates"]);
  assert.deepEqual(at("/payments"), ["finance", "/payments"]);
  assert.deepEqual(at("/settings/grading"), ["settings", "/settings/grading"]);
  assert.deepEqual(at("/leads/42"), ["sales", "/leads"]);
  assert.equal(at("/profile"), undefined);
  assert.equal(at("/studentsx"), undefined);
  // a page of a tab the user cannot see belongs to no hub
  assert.equal(activeHub(visibleHubs(instructor, "instructor", true), "/students/1"), undefined);
  assert.equal(tabOf(hubs[3], "/rooms")?.label, "Расписание");
});

test("phone: four hubs in the bar, the rest goes to «Ещё»", () => {
  const { main, more } = splitNav(visibleHubs(everything, "manager"), "manager");
  assert.deepEqual(main.map((h) => h.key), ["dashboard", "sales", "study", "finance"]);
  assert.deepEqual(more.map((h) => h.key), ["today", "settings"]); // «Настройки» last
  assert.deepEqual(splitNav(visibleHubs(instructor, "instructor", true), "instructor").more, []);
});

test("phone: without finance (or for the instructor) the bar is the first four hubs", () => {
  const withToday = { ...manager, attendance: "view", payments: undefined } as Permissions;
  assert.deepEqual(splitNav(visibleHubs(withToday, "manager"), "manager").main.map((h) => h.key), ["dashboard", "today", "sales", "study"]);
  const boss = visibleHubs(everything, "instructor", true);
  // the instructor role never sees «Дашборд» (staff only)
  assert.deepEqual(splitNav(boss, "instructor").main.map((h) => h.key), ["today", "sales", "study", "finance"]);
  assert.deepEqual(splitNav(boss, "instructor").more.map((h) => h.key), ["settings"]);
});

test("home is the first visible section, the profile when there is none", () => {
  assert.equal(homePath(manager), "/dashboard");
  assert.equal(homePath(instructor, "instructor", true), "/today"); // the instructor lands on «Сегодня»
  assert.equal(homePath({}), "/profile");
});

test("canOpen guards sections, not the profile", () => {
  assert.equal(canOpen(instructor, "/users"), false);
  assert.equal(canOpen(instructor, "/today"), true);
  assert.equal(canOpen(manager, "/today"), false); // no attendance right
  assert.equal(canOpen(instructor, "/profile"), true);
  assert.equal(canOpen({}, "/roles"), false);
});

test("matrix: none rows are dropped, change is one column", () => {
  const sections = ["leads", "audit", "users"];
  const matrix = toMatrix({ leads: "change", audit: "view" }, sections);
  assert.deepEqual(matrix, { leads: "change", audit: "view", users: "none" });
  const edited: Record<string, MatrixChoice> = { ...toMatrix({ leads: "change", audit: "view" }, sections), audit: "none" };
  assert.deepEqual(fromMatrix(edited), { leads: "change" });
});

test("the registry is in the nav for a user with the certificates section", () => {
  assert.equal(visibleNav({ certificates: "view" }).some((i) => i.href === "/certificates"), true);
  assert.equal(visibleNav({ cert_templates: "view" }).some((i) => i.href === "/certificates"), true);
  assert.equal(canOpen({ cohorts: "view" }, "/certificates"), false);
  assert.equal(canOpen({ certificates: "view" }, "/certificates"), true);
});

test("certificates: one menu item, shown for registry or templates right", () => {
  const hrefs = (p: Record<string, "view" | "change">) => visibleNav(p, "manager").map((i) => i.href);
  assert.deepEqual(hrefs({ certificates: "view" }), ["/certificates"]);
  assert.deepEqual(hrefs({ cert_templates: "view" }), ["/certificates"]);
  assert.equal(NAV_ITEMS.some((i) => i.href === "/settings/certificates"), false);
  assert.equal(canOpen({ cert_templates: "view" }, "/settings/certificates/abc", "manager"), true);
  assert.equal(canOpen({ certificates: "view" }, "/settings/certificates", "manager"), false);
});
