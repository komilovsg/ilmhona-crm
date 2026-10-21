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
await browser.close();

if (bad.length) {
  console.error(`FAIL: content not visible: ${bad.join("; ")}`);
  process.exit(1);
}
console.log("OK: public pages are visible under reduced motion");
