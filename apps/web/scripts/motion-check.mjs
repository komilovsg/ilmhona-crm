#!/usr/bin/env node
// Reduced-motion check: the public pages must be VISIBLE (computed opacity 1 on the element and all its
// ancestors, no hidden transform) with prefers-reduced-motion: reduce, with JavaScript off (server HTML only)
// and normally once the entrance animation is over.
//
//   WEB_URL=http://localhost:3510 pnpm motion
//
// Needs the web running (production build) and a Chromium for playwright-core.

import { chromium } from "playwright-core";

const BASE = process.env.WEB_URL ?? "http://localhost:3510";
const PAGES = [
  { path: "/login", probe: "form" },
  { path: "/forgot-password", probe: "form" },
];

const effectiveOpacity = (selector) => {
  let el = document.querySelector(selector);
  let o = 1;

  if (!el) return -1;
  for (; el; el = el.parentElement) o *= Number(getComputedStyle(el).opacity);

  return o;
};

const browser = await chromium.launch();
const bad = [];

for (const [label, ctxOptions] of [
  ["reduced motion", { reducedMotion: "reduce" }],
  ["reduced motion, no JS", { reducedMotion: "reduce", javaScriptEnabled: false }],
  ["normal", {}],
]) {
  const context = await browser.newContext(ctxOptions);

  for (const { path, probe } of PAGES) {
    const page = await context.newPage();

    await page.goto(`${BASE}${path}`, { waitUntil: "load" });
    await page.waitForTimeout(1000);
    const opacity = await page.evaluate(effectiveOpacity, probe);

    console.log(`${label.padEnd(24)} ${path.padEnd(18)} opacity ${opacity}`);
    if (opacity !== 1) bad.push(`${label} ${path}: ${opacity}`);
    await page.close();
  }
  await context.close();
}
// Overlays under reduced motion (needs a login: CRM_LOGIN / CRM_PASSWORD): open a modal and fire a toast,
// sample the transform of the dialog and of the toast (and its wrapper) every frame; none may move or scale.
if (process.env.CRM_LOGIN && process.env.CRM_PASSWORD) {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });
  const login = await context.request.post(`${BASE}/api/v1/auth/login`, {
    headers: { "X-Requested-With": "ilm" },
    data: { login: process.env.CRM_LOGIN, password: process.env.CRM_PASSWORD },
  });

  if (!login.ok()) throw new Error(`login failed: ${login.status()}`);
  const page = await context.newPage();

  await page.route("**/export*", (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
  await page.goto(`${BASE}/students`, { waitUntil: "networkidle" });
  await page.evaluate(() => {
    window.__frames = { dialog: new Set(), toast: new Set(), seen: { dialog: 0, toast: 0 } };
    const moving = (t) => t !== "none" && t !== "matrix(1, 0, 0, 1, 0, 0)";
    const tick = () => {
      for (const el of document.querySelectorAll('[role="dialog"]')) {
        window.__frames.seen.dialog++;
        if (moving(getComputedStyle(el).transform)) window.__frames.dialog.add(getComputedStyle(el).transform);
      }
      for (const el of document.querySelectorAll("[data-toast]")) {
        window.__frames.seen.toast++;
        for (const n of [el, el.closest("li")]) if (n && moving(getComputedStyle(n).transform)) window.__frames.toast.add(getComputedStyle(n).transform);
      }
      requestAnimationFrame(tick);
    };

    tick();
  });
  await page.getByRole("button", { name: /Студент/ }).first().click(); // «+ Студент»: the form modal
  await page.waitForTimeout(700);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: /Excel/ }).first().click(); // the failing export fires an error toast
  await page.waitForTimeout(900);
  const f = await page.evaluate(() => ({ dialog: [...window.__frames.dialog], toast: [...window.__frames.toast], seen: window.__frames.seen }));

  console.log(`overlays (reduced)       dialog frames ${f.seen.dialog}, moving: ${f.dialog.length}; toast frames ${f.seen.toast}, moving: ${f.toast.length}`);
  if (!f.seen.dialog || !f.seen.toast) bad.push("overlay did not open (modal or toast not seen)");
  if (f.dialog.length) bad.push(`modal moves/scales under reduced motion: ${f.dialog.slice(0, 3)}`);
  if (f.toast.length) bad.push(`toast moves/scales under reduced motion: ${f.toast.slice(0, 3)}`);
  await context.close();
}
await browser.close();

if (bad.length) {
  console.error(`FAIL: content not visible: ${bad.join("; ")}`);
  process.exit(1);
}
console.log("OK: public pages are visible under reduced motion");
