#!/usr/bin/env node
// Render error -> Sentry check: one render error reaches the monitoring tunnel as exactly ONE error
// event, with nothing personal in it. The ingest is fake: the browser's POST to /monitoring is
// answered here, nothing leaves the machine.
//
//   NEXT_PUBLIC_SENTRY_DSN=https://k@o1.ingest.sentry.io/1 pnpm build   (the DSN is inlined at build time)
//   WEB_URL=http://localhost:3780 CRM_LOGIN=demo_admin CRM_PASSWORD=... pnpm sentry
//
// Needs the web built WITH a (fake) DSN, its API, and a Chromium for playwright-core.

import { chromium } from "playwright-core";

const BASE = process.env.WEB_URL ?? "http://localhost:3780";
const LOGIN = process.env.CRM_LOGIN;
const PASSWORD = process.env.CRM_PASSWORD;

if (!LOGIN || !PASSWORD) {
  console.error("Set CRM_LOGIN and CRM_PASSWORD.");
  process.exit(2);
}

// fake personal data placed where it could leak: the page URL (query) and the failing response
const FAKE_PHONE = "992900123456";
const FAKE_EMAIL = "fake.person@example.test";
const failures = [];
const check = (ok, what) => {
  if (!ok) failures.push(what);
};

const browser = await chromium.launch();
const context = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 900 } });
const login = await context.request.post("/api/v1/auth/login", {
  headers: { "X-Requested-With": "ilm" },
  data: { login: LOGIN, password: PASSWORD },
});

if (!login.ok()) throw new Error(`login failed: ${login.status()}`);
const cookies = (await context.cookies()).map((c) => c.value).filter((v) => v.length > 12);
const envelopes = [];
const page = await context.newPage();

page.on("pageerror", () => {});
await page.route("**/monitoring", async (route) => {
  envelopes.push(route.request().postData() ?? "");
  await route.fulfill({ status: 200, body: "" });
});
await page.route("**/api/v1/students?**", (route) =>
  route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [null], total: 1, page: 1, page_size: 25, summary: {} }),
  }),
);
await page.goto(`/students?search=${FAKE_PHONE}&e=${FAKE_EMAIL}`, { waitUntil: "networkidle" });
await page.getByRole("heading", { name: "Что-то пошло не так" }).waitFor({ timeout: 10000 });
await page.waitForTimeout(3000); // the SDK flushes in the background

const events = [];

for (const raw of envelopes) {
  const lines = raw.split("\n");

  // envelope = header line, then pairs of (item header, payload)
  for (let i = 1; i + 1 < lines.length; i += 2) {
    try {
      if (JSON.parse(lines[i]).type === "event") events.push(lines[i + 1]);
    } catch {
      // not JSON: ignore
    }
  }
}
console.log(`envelopes ${envelopes.length}, error events ${events.length}`);
check(events.length === 1, `expected exactly one error event for one render error, got ${events.length}`);
const all = envelopes.join("\n");

check(!all.includes(FAKE_PHONE), "the phone number from the URL query leaked into an envelope");
check(!all.includes(FAKE_EMAIL), "the e-mail from the URL query leaked into an envelope");
check(!/search=|[?&]e=/.test(all), "a URL query leaked into an envelope");
for (const v of cookies) check(!all.includes(v), "a cookie value leaked into an envelope");
check(!/cookie/i.test(events.join("")) || !/ilm_access/.test(events.join("")), "the session cookie is in the event");
await browser.close();

if (failures.length) {
  console.error(`FAIL:\n  ${failures.join("\n  ")}`);
  process.exit(1);
}
console.log("OK: one render error -> one scrubbed error event");
