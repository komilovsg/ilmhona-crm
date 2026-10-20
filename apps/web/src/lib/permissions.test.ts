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
    visibleNav(instructor).map((i) => i.section),
    ["attendance", "cohorts", "instructors"],
  );
  assert.deepEqual(visibleNav(undefined), []);
  assert.equal(visibleNav(manager).some((i) => i.section === "users"), false);
});

test("users section opens both Пользователи and Роли, audit is separate", () => {
  const nav = visibleNav({ users: "view" }).map((i) => i.href);
  assert.deepEqual(nav, ["/users", "/roles"]);
  assert.deepEqual(visibleNav({ audit: "view" }).map((i) => i.href), ["/audit"]);
});

test("every backend section has a nav item", () => {
  const sections = new Set(NAV_ITEMS.map((i) => i.section));
  assert.equal(sections.size, 13);
});

test("phone: four main items, the rest goes to «Ещё»", () => {
  const all = Object.fromEntries(NAV_ITEMS.map((i) => [i.section, "change"])) as Permissions;
  const { main, more } = splitNav(visibleNav(all));
  assert.equal(main.length, 4);
  assert.equal(more.length, NAV_ITEMS.length - 4);
  assert.deepEqual(splitNav(visibleNav(instructor)).more, []);
});

test("home is the first visible section, the profile when there is none", () => {
  assert.equal(homePath(manager), "/dashboard");
  assert.equal(homePath(instructor), "/today"); // the instructor lands on «Сегодня»
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
