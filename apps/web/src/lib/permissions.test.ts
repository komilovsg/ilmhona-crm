import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allows,
  canOpen,
  fromMatrix,
  homePath,
  NAV_ITEMS,
  splitNav,
  toMatrix,
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
  const sections = new Set(NAV_ITEMS.map((i) => i.section));
  assert.equal(sections.size, 16);
});

test("phone: four main items, the rest goes to «Ещё»", () => {
  const all = Object.fromEntries(NAV_ITEMS.map((i) => [i.section, "change"])) as Permissions;
  const { main, more } = splitNav(visibleNav(all, "manager"));
  assert.equal(main.length, 4);
  assert.equal(more.length, NAV_ITEMS.length - 1 - 4); // minus «Мои выплаты» (instructor only)
  assert.deepEqual(splitNav(visibleNav(instructor, "instructor", true)).more, []);
});

test("phone: users who see payments get Дашборд, Лиды, Студенты, Оплаты; «Сегодня» goes to «Ещё»", () => {
  const withToday = { ...manager, attendance: "view" } as Permissions;
  const { main, more } = splitNav(visibleNav(withToday, "manager"), "manager");
  assert.deepEqual(main.map((i) => i.href), ["/dashboard", "/leads", "/students", "/payments"]);
  assert.ok(more.some((i) => i.href === "/today"));
  // without payments nothing changes: the first four
  const noPay = { ...withToday, payments: undefined } as Permissions;
  assert.deepEqual(splitNav(visibleNav(noPay, "manager"), "manager").main.map((i) => i.href), ["/dashboard", "/today", "/leads", "/students"]);
  // the instructor's bar is unchanged
  assert.deepEqual(splitNav(visibleNav(instructor, "instructor", true), "instructor").main.map((i) => i.href), splitNav(visibleNav(instructor, "instructor", true)).main.map((i) => i.href));
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
  assert.equal(visibleNav({ cert_templates: "view" }).some((i) => i.href === "/certificates"), false);
  assert.equal(canOpen({ cohorts: "view" }, "/certificates"), false);
  assert.equal(canOpen({ certificates: "view" }, "/certificates"), true);
});
