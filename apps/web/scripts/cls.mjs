#!/usr/bin/env node
// Layout-shift (CLS) check of every page with a slowed-down API.
//
//   WEB_URL=http://localhost:3290 CRM_LOGIN=root CRM_PASSWORD=... pnpm cls
//
// For each page and for desktop (1440) and phone (390) it opens the page with every
// /api/v1 response delayed by API_DELAY_MS (default 1200), sums the layout-shift entries that did
// not follow user input until the page is idle, and fails (exit 1) when a page is over 0.1.
// A page that is still showing a skeleton after the wait also fails: loading must end.
// Needs: the web on WEB_URL with its API, a user who can open every section (superadmin), and a
// Chromium for playwright-core (`pnpm exec playwright-core install chromium` once).

import { chromium } from "playwright-core";

const BASE = process.env.WEB_URL ?? "http://localhost:3290";
const LOGIN = process.env.CRM_LOGIN;
const PASSWORD = process.env.CRM_PASSWORD;
const DELAY = Number(process.env.API_DELAY_MS ?? 1200);
const LIMIT = Number(process.env.CLS_LIMIT ?? 0.1);

if (!LOGIN || !PASSWORD) {
  console.error("Set CRM_LOGIN and CRM_PASSWORD (a user that may open every section).");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "desktop 1440", width: 1440, height: 900 },
  { name: "phone 390", width: 390, height: 844 },
];

const observe = () => {
  window.__cls = 0;
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
  }).observe({ type: "layout-shift", buffered: true });
};

const browser = await chromium.launch();
const results = [];

for (const vp of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  const login = await context.request.post(`${BASE}/api/v1/auth/login`, {
    headers: { "X-Requested-With": "ilm" },
    data: { login: LOGIN, password: PASSWORD },
  });

  if (!login.ok()) {
    console.error(`login failed: ${login.status()}`);
    process.exit(2);
  }

  const get = async (path) => (await context.request.get(`${BASE}${path}`)).json();
  const cohort = (await get("/api/v1/cohorts?page_size=1")).items?.[0];
  const student = (await get("/api/v1/students?page_size=1")).items?.[0];
  const pages = [
    "/dashboard",
    "/users",
    "/roles",
    "/audit",
    "/profile",
    "/rooms",
    "/payments",
    "/instructors",
    "/salaries",
    "/cohorts",
    ...(cohort ? [`/cohorts/${cohort.id}`] : []),
    "/students",
    ...(student ? [`/students/${student.id}`] : []),
  ];

  for (const path of pages) {
    const page = await context.newPage();

    await page.addInitScript(observe);
    // a slow API: every call waits DELAY ms, so skeletons and the swap to data are really exercised
    await page.route("**/api/v1/**", async (route) => {
      const response = await route.fetch();

      await new Promise((r) => setTimeout(r, DELAY));
      await route.fulfill({ response });
    });
    await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(DELAY + 800);

    const cls = await page.evaluate(() => window.__cls);
    const stuck = await page.locator('[aria-busy="true"]').count();

    results.push({ viewport: vp.name, path: path.replace(/[0-9a-f-]{36}/, ":id"), cls: Number(cls.toFixed(4)), stuck });
    await page.close();
  }
  await context.close();
}
await browser.close();

console.table(results);

const bad = results.filter((r) => r.cls > LIMIT || r.stuck > 0);

if (bad.length) {
  console.error(`FAIL: ${bad.length} page(s) over CLS ${LIMIT} or still loading`);
  process.exit(1);
}
console.log(`OK: every page under CLS ${LIMIT}`);
