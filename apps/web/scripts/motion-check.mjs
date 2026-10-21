#!/usr/bin/env node
// Reduced-motion check.
//
//   WEB_URL=http://localhost:3560 CRM_LOGIN=root CRM_PASSWORD=... pnpm motion
//
// 1. /login and /forgot-password are VISIBLE (effective opacity 1) under prefers-reduced-motion, with JavaScript
//    off (server HTML only) and normally once the entrance is over.
// 2. Overlays (needs CRM_LOGIN / CRM_PASSWORD of a superadmin): modal, drawer at 390 px (page filters and the
//    bottom-nav «Ещё»), toast, dropdown, select and tooltip are opened and closed while every animation frame
//    records getBoundingClientRect() and the computed transform of the overlay element, its [data-slot=wrapper],
//    its [data-slot=base] and every ancestor up to <body>. Normal mode: each overlay MUST move (proves the probe
//    sees the animation, so the check can fail). Reduced motion, set before load and toggled after load: nothing
//    may move or scale (rect constant, one transform value per element) while it is visible. Opacity fades are allowed.
//
// Needs the web running (production build) with its API, and a Chromium for playwright-core.

import { chromium } from "playwright-core";

const BASE = process.env.WEB_URL ?? "http://localhost:3560";
const LOGIN = process.env.CRM_LOGIN;
const PASSWORD = process.env.CRM_PASSWORD;
const bad = [];
const browser = await chromium.launch();

// ---- 1. public pages visible --------------------------------------------------------------------------------
const effectiveOpacity = (selector) => {
  let el = document.querySelector(selector);
  let o = 1;

  if (!el) return -1;
  for (; el; el = el.parentElement) o *= Number(getComputedStyle(el).opacity);

  return o;
};

for (const [label, ctxOptions] of [
  ["reduced motion", { reducedMotion: "reduce" }],
  ["reduced motion, no JS", { reducedMotion: "reduce", javaScriptEnabled: false }],
  ["normal", {}],
]) {
  const context = await browser.newContext(ctxOptions);

  for (const path of ["/login", "/forgot-password"]) {
    const page = await context.newPage();

    await page.goto(`${BASE}${path}`, { waitUntil: "load" });
    await page.waitForTimeout(1000);
    const opacity = await page.evaluate(effectiveOpacity, "form");

    console.log(`${label.padEnd(24)} ${path.padEnd(18)} opacity ${opacity}`);
    if (opacity !== 1) bad.push(`${label} ${path}: opacity ${opacity}`);
    await page.close();
  }
  await context.close();
}

// ---- 2. overlays ----------------------------------------------------------------------------------------------
// Runs in the page: every frame, for each element matching `selector`, record the rect and transform of the
// element, its wrapper / base slots and all ancestors up to body.
const installProbe = (selector) => {
  const seen = new Map(); // element -> { rects: Set, transforms: Set, name }
  const probe = { frames: 0, seen };
  const name = (el) => `${el.tagName.toLowerCase()}${el.dataset.slot ? `[slot=${el.dataset.slot}]` : ""}${el.getAttribute("role") ? `[role=${el.getAttribute("role")}]` : ""}`;
  const note = (el) => {
    const r = el.getBoundingClientRect();
    const rec = seen.get(el) ?? { rects: [], transforms: new Set(), name: name(el) };

    rec.rects.push([r.x, r.y, r.width, r.height]);
    rec.transforms.add(getComputedStyle(el).transform);
    seen.set(el, rec);
  };
  const tick = () => {
    if (window.__probe !== probe) return;
    for (const root of document.querySelectorAll(selector)) {
      let opacity = 1;

      for (let el = root; el; el = el.parentElement) opacity *= Number(getComputedStyle(el).opacity);
      if (opacity === 0) continue; // not painted yet (e.g. a toast before its first placement): nothing is seen moving
      probe.frames++;
      const set = new Set([root, root.closest("[data-slot=wrapper]"), root.closest("[data-slot=base]"), root.querySelector("[data-slot=wrapper]"), root.querySelector("[data-slot=base]")]);

      for (let el = root.parentElement; el && el !== document.documentElement; el = el.parentElement) set.add(el);
      for (const el of set) if (el) note(el);
    }
    requestAnimationFrame(tick);
  };

  window.__probe = probe;
  requestAnimationFrame(tick);
};

const readProbe = () => {
  const probe = window.__probe;
  let px = 0;
  let worst = "";
  let transforms = 0;
  let scaled = "";

  window.__probe = null;
  for (const rec of probe.seen.values()) {
    for (let i = 0; i < 4; i++) {
      const vals = rec.rects.map((r) => r[i]);
      const d = Math.max(...vals) - Math.min(...vals);

      if (d > px) [px, worst] = [d, `${rec.name} ${["x", "y", "width", "height"][i]} ${Math.min(...vals).toFixed(1)}..${Math.max(...vals).toFixed(1)}`];
    }
    if (rec.transforms.size > 1) {
      transforms++;
      scaled ||= `${rec.name}: ${[...rec.transforms].slice(0, 3).join(" | ")}`;
    }
  }

  return { frames: probe.frames, px: Math.round(px * 10) / 10, worst, transforms, scaled };
};

async function measure(page, selector, open, close) {
  await page.evaluate(installProbe, selector);
  await open();
  await page.waitForTimeout(800);
  await close();
  await page.waitForTimeout(600);
  const r = await page.evaluate(readProbe);

  r.closed = !(await page.locator(selector).count());

  return r;
}

async function loggedIn(mode, viewport) {
  const context = await browser.newContext({ viewport, ...(mode === "reduced before load" ? { reducedMotion: "reduce" } : {}) });
  const login = await context.request.post(`${BASE}/api/v1/auth/login`, {
    headers: { "X-Requested-With": "ilm" },
    data: { login: LOGIN, password: PASSWORD },
  });

  if (!login.ok()) throw new Error(`login failed: ${login.status()}`);

  return context;
}

async function goto(context, mode, path, init) {
  const page = await context.newPage();

  if (init) await page.addInitScript(init);
  // the export fails on purpose: its error toast is the toast under test
  await page.route("**/export*", (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  if (mode === "reduced toggled") await page.emulateMedia({ reducedMotion: "reduce" });
  await page.waitForTimeout(300);

  return page;
}

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const esc = (page) => () => page.keyboard.press("Escape");

const CASES = [
  {
    name: "modal",
    viewport: DESKTOP,
    path: "/students",
    selector: '[role="dialog"]',
    open: (p) => p.getByRole("button", { name: /Студент/ }).first().click(),
    close: esc,
  },
  {
    name: "toast",
    viewport: DESKTOP,
    path: "/students",
    selector: "[data-toast]",
    open: (p) => p.getByRole("button", { name: /Excel/ }).first().click(),
    // closed from the keyboard: a pointer over the stack expands it (an instant re-layout, not motion)
    close: (p) => async () => {
      await p.locator("[data-toast] button[aria-label=closeButton]").first().focus();
      await p.keyboard.press("Enter");
    },
  },
  {
    name: "dropdown",
    viewport: DESKTOP,
    path: "/students",
    selector: '[role="menu"]',
    open: (p) => p.getByRole("button", { name: /Суперадмин/ }).first().click(),
    close: esc,
  },
  {
    name: "select",
    viewport: DESKTOP,
    path: "/payments",
    selector: '[role="listbox"]',
    open: (p) => p.getByRole("button", { name: /Статус/ }).first().click(),
    close: esc,
  },
  {
    name: "tooltip",
    viewport: DESKTOP,
    path: "/students",
    init: () => localStorage.setItem("ilm-sidebar", "collapsed"),
    selector: '[role="tooltip"]',
    // react-aria opens a tooltip on a real pointer move (a bare hover() is not enough)
    open: async (p) => {
      const box = await p.locator('nav[aria-label="Разделы"] a').nth(1).boundingBox();

      await p.mouse.move(600, 400);
      await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 5 });
    },
    close: (p) => () => p.mouse.move(900, 600),
  },
  {
    name: "drawer filters 390",
    viewport: PHONE,
    path: "/payments",
    selector: '[role="dialog"]',
    open: (p) => p.getByRole("button", { name: /Фильтры/ }).first().click(),
    close: esc,
  },
  {
    name: "drawer «Ещё» 390",
    viewport: PHONE,
    path: "/students",
    selector: '[role="dialog"]',
    open: (p) => p.getByRole("navigation", { name: "Основное меню" }).getByRole("button", { name: /Ещё/ }).click(),
    close: esc,
  },
];

if (LOGIN && PASSWORD) {
  for (const mode of ["normal", "reduced before load", "reduced toggled"]) {
    for (const c of CASES) {
      const context = await loggedIn(mode, c.viewport);
      const page = await goto(context, mode, c.path, c.init);
      const r = await measure(page, c.selector, () => c.open(page), c.close(page));
      const moved = r.px > 0 || r.transforms > 0;

      console.log(`${mode.padEnd(20)} ${c.name.padEnd(20)} frames ${String(r.frames).padStart(3)}  moved ${String(r.px).padStart(6)} px  transform changes ${r.transforms}${moved ? `  (${r.worst || r.scaled})` : ""}`);
      if (!r.frames) bad.push(`${mode} ${c.name}: overlay never opened`);
      else if (!r.closed) bad.push(`${mode} ${c.name}: overlay did not close`);
      else if (mode === "normal" && !moved) bad.push(`normal ${c.name}: no movement seen, the probe cannot catch a regression`);
      else if (mode !== "normal" && moved) bad.push(`${mode} ${c.name}: moves ${r.px} px / ${r.transforms} transform changes (${r.worst} ${r.scaled})`);
      await context.close();
    }
  }
} else {
  console.log("overlays skipped: set CRM_LOGIN and CRM_PASSWORD");
}
await browser.close();

if (bad.length) {
  console.error(`FAIL:\n  ${bad.join("\n  ")}`);
  process.exit(1);
}
console.log("OK: public pages visible; overlays move normally and stand still under reduced motion");
