#!/usr/bin/env node
// Error screens check: unknown routes answer 404 with the Russian page, and a render error shows
// the Russian boundary (shell stays, «Повторить», no stack), at 1440 and 390, light and dark.
//
//   WEB_URL=http://localhost:3680 CRM_LOGIN=demo_admin CRM_PASSWORD=... pnpm errors
//   SHOTS=/some/dir  (optional) saves a screenshot of every state
//
// Needs the web on WEB_URL with its API (a production build shows the real CSP), and a Chromium
// for playwright-core. Violations of the CSP in the console fail the check.

import { chromium } from "playwright-core";

const BASE = process.env.WEB_URL ?? "http://localhost:3680";
const LOGIN = process.env.CRM_LOGIN;
const PASSWORD = process.env.CRM_PASSWORD;
const SHOTS = process.env.SHOTS;

if (!LOGIN || !PASSWORD) {
  console.error("Set CRM_LOGIN and CRM_PASSWORD.");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
];
const SCHEMES = ["light", "dark"];
const failures = [];
const check = (ok, what) => {
  if (!ok) failures.push(what);
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
};

const browser = await chromium.launch();

for (const vp of VIEWPORTS) {
  for (const scheme of SCHEMES) {
    const tag = `${vp.name} ${scheme}`;
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      colorScheme: scheme,
      baseURL: BASE,
    });
    const login = await context.request.post(`${BASE}/api/v1/auth/login`, {
      headers: { "X-Requested-With": "ilm" },
      data: { login: LOGIN, password: PASSWORD },
    });
    if (!login.ok()) {
      console.error(`login failed: ${login.status()}`);
      process.exit(2);
    }
    const shot = async (page, name) => {
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}-${vp.name}-${scheme}.png` });
    };

    // 1. unknown routes: 404 status, the Russian page, the shell around it
    for (const path of ["/net-takoy-stranitsy", "/net/takoy/stranitsy", "/students/not-a-uuid-at-all/x", "/students/00000000-0000-4000-8000-000000000001", "/cohorts/00000000-0000-4000-8000-000000000001"]) {
      const page = await context.newPage();
      const csp = [];
      page.on("console", (m) => /content security policy/i.test(m.text()) && csp.push(m.text()));
      const res = await page.goto(path, { waitUntil: "networkidle" });
      check(res.status() === 404, `${tag} ${path}: status 404 (got ${res.status()})`);
      check(await page.getByRole("heading", { name: "Страница не найдена" }).isVisible(), `${tag} ${path}: Russian 404 title`);
      check(await page.getByText("На главную", { exact: true }).isVisible(), `${tag} ${path}: «На главную»`);
      check(await page.getByText("Назад", { exact: true }).isVisible(), `${tag} ${path}: «Назад»`);
      check(csp.length === 0, `${tag} ${path}: no CSP violation`);
      check((await page.locator("aside, nav").count()) > 0, `${tag} ${path}: the shell stays`);
      await shot(page, `404${path.replaceAll("/", "_")}`);
      await page.close();
    }

    // 2. a render error: the students list gets data that cannot be rendered
    {
      const page = await context.newPage();
      const csp = [];
      page.on("console", (m) => /content security policy/i.test(m.text()) && csp.push(m.text()));
      page.on("pageerror", () => {}); // the thrown render error is the point
      let broken = true;
      await page.route("**/api/v1/students?**", async (route) => {
        if (!broken) return route.continue();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [null], total: 1, page: 1, page_size: 25, summary: {} }),
        });
      });
      await page.goto("/students", { waitUntil: "networkidle" });
      await page.getByRole("heading", { name: "Что-то пошло не так" }).waitFor({ timeout: 10000 });
      check(true, `${tag} render error: Russian boundary title`);
      check(await page.getByRole("button", { name: "Повторить" }).isVisible(), `${tag} render error: «Повторить»`);
      check(await page.getByText("На главную", { exact: true }).isVisible(), `${tag} render error: «На главную»`);
      check(await page.getByText("Код ошибки").isVisible(), `${tag} render error: support code line`);
      const body = await page.locator("body").innerText();
      check(!/at \w+ \(|\.tsx?:\d+|TypeError|Cannot read/.test(body), `${tag} render error: no stack or JS message on screen`);
      check((await page.locator("aside, nav").count()) > 0, `${tag} render error: the shell stays`);
      check(csp.length === 0, `${tag} render error: no CSP violation`);
      await shot(page, "error");
      // «Повторить» recovers once the data is fine
      broken = false;
      await page.getByRole("button", { name: "Повторить" }).click();
      await page.getByRole("heading", { name: "Что-то пошло не так" }).waitFor({ state: "detached", timeout: 10000 });
      check(true, `${tag} render error: «Повторить» recovers`);
      await page.close();
    }
    await context.close();
  }
}
await browser.close();

if (failures.length) {
  console.error(`FAIL: ${failures.length} check(s)\n${failures.join("\n")}`);
  process.exit(1);
}
console.log("OK: 404 and error screens");
