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
// 3. Gestures (needs the same login): phone toast (top, tap does not dismiss, swipe up / sideways does), bottom sheet
//    (follows the finger even under reduced motion, springs back on a short slow drag, closes on a far / fast
//    one), unsaved-changes guard on swipe / Esc / backdrop (phone and desktop).
//
// Needs the web running (production build) with its API, and a Chromium for playwright-core.

import { chromium } from "playwright-core";

const BASE = process.env.WEB_URL ?? "http://localhost:3560";
const LOGIN = process.env.CRM_LOGIN;
const PASSWORD = process.env.CRM_PASSWORD;
// MOTION_ONLY=gestures runs part 3 alone (quick loop while working on it); the full run is the gate
const ONLY = process.env.MOTION_ONLY;
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

for (const [label, ctxOptions] of ONLY ? [] : [
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
  const context = await browser.newContext({ viewport, hasTouch: viewport.width < 768, ...(mode === "reduced before load" ? { reducedMotion: "reduce" } : {}) });
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

const closeToast = (p) => async () => {
  await p.locator('[data-toast] button[aria-label="Закрыть уведомление"]').first().focus();
  await p.keyboard.press("Enter");
};

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
    // closed from the keyboard: a pointer over the stack only pauses it, but keeps the probe honest
    close: closeToast,
  },
  {
    name: "toast 390",
    viewport: PHONE,
    path: "/students",
    selector: "[data-toast]",
    open: (p) => p.getByRole("button", { name: /Excel/ }).first().click(),
    close: closeToast,
  },
  {
    name: "modal sheet 390",
    viewport: PHONE,
    path: "/students",
    selector: '[role="dialog"]',
    open: (p) => p.getByRole("button", { name: /Студент/ }).first().click(),
    close: esc,
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

if (LOGIN && PASSWORD && !ONLY) {
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
} else if (!ONLY) {
  console.log("overlays skipped: set CRM_LOGIN and CRM_PASSWORD");
}

// ---- 3. gestures ------------------------------------------------------------------------------------------------
async function touchSwipe(page, [x0, y0], [x1, y1], { steps = 10, gap = 14 } = {}) {
  const cdp = await page.context().newCDPSession(page);
  const send = (type, pts) => cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts });

  await send("touchStart", [{ x: x0, y: y0 }]);
  for (let i = 1; i <= steps; i++) {
    await send("touchMove", [{ x: x0 + ((x1 - x0) * i) / steps, y: y0 + ((y1 - y0) * i) / steps }]);
    await page.waitForTimeout(gap);
  }

  return { release: () => send("touchEnd", []) };
}

const rectOf = (page, sel) =>
  page.locator(sel).first().evaluate((e) => {
    const r = e.getBoundingClientRect();

    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
const count = (page, sel) => page.locator(sel).count();
const expect = (cond, msg) => {
  if (!cond) bad.push(msg);
};

if (LOGIN && PASSWORD) {
  for (const mode of ["normal", "reduced before load", "reduced toggled"]) {
    const tag = `${mode} gestures`;

    // -- phone toast
    {
      const context = await loggedIn(mode, PHONE);
      const page = await goto(context, mode, "/students");
      const exportBtn = page.getByRole("button", { name: /Excel/ }).first();

      await exportBtn.click();
      await page.locator("[data-toast]").first().waitFor();
      await page.waitForTimeout(700);
      const r0 = await rectOf(page, "[data-toast] > div");
      const cy = r0.y + r0.h / 2;

      expect(r0.y < 100 && r0.y >= 0, `${tag}: toast not at the top (y ${r0.y})`);
      await page.touchscreen.tap(r0.x + 40, cy); // a tap
      await page.waitForTimeout(500);
      expect((await count(page, "[data-toast]")) === 1, `${tag}: a tap dismissed the toast`);
      const nudge = await touchSwipe(page, [150, cy], [150, cy - 12], { steps: 3 });

      await nudge.release();
      await page.waitForTimeout(600);
      expect((await count(page, "[data-toast]")) === 1, `${tag}: a 12 px nudge dismissed the toast`);
      const up = await touchSwipe(page, [150, cy], [150, cy - 70], { steps: 6 });
      const mid = await rectOf(page, "[data-toast] > div");

      expect(r0.y - mid.y > 30, `${tag}: the toast did not follow the finger (${r0.y} -> ${mid.y})`);
      await up.release();
      await page.waitForTimeout(900);
      expect((await count(page, "[data-toast]")) === 0, `${tag}: swipe up did not dismiss the toast`);
      await exportBtn.click();
      await page.locator("[data-toast]").first().waitFor();
      await page.waitForTimeout(700);
      const r1 = await rectOf(page, "[data-toast] > div");
      const side = await touchSwipe(page, [100, r1.y + r1.h / 2], [300, r1.y + r1.h / 2], { steps: 6 });

      await side.release();
      await page.waitForTimeout(900);
      expect((await count(page, "[data-toast]")) === 0, `${tag}: swipe sideways did not dismiss the toast`);
      console.log(`${tag.padEnd(28)} phone toast: top, tap + nudge ignored, swipe up and sideways dismiss`);
      await context.close();
    }

    // -- phone sheet + unsaved-changes guard
    {
      const context = await loggedIn(mode, PHONE);
      const page = await goto(context, mode, "/students");
      const dlg = '[role="dialog"]';
      const open = async () => {
        await page.getByRole("button", { name: /Студент/ }).first().click();
        await page.locator(dlg).first().waitFor();
        await page.waitForTimeout(800);
      };
      const ask = page.getByText("Закрыть без сохранения?");

      await open();
      const rest = await rectOf(page, dlg);

      expect(rest.y + rest.h <= 845 && rest.y > 40, `${tag}: not a bottom sheet (${JSON.stringify(rest)})`);
      // slow, short drag from the handle: follows the finger, springs back
      const slow = await touchSwipe(page, [195, rest.y + 10], [195, rest.y + 70], { steps: 6, gap: 60 });
      const held = await rectOf(page, dlg);

      expect(held.y - rest.y > 30 && held.y - rest.y < 62, `${tag}: sheet does not follow the finger (${rest.y} -> ${held.y})`);
      await slow.release();
      await page.waitForTimeout(700);
      const back = await rectOf(page, dlg);

      expect(Math.abs(back.y - rest.y) < 2 && (await count(page, dlg)) === 1, `${tag}: short slow drag did not spring back`);
      // pulling up: rubber band, never 1:1
      const pull = await touchSwipe(page, [195, rest.y + 10], [195, rest.y - 90], { steps: 6, gap: 20 });
      const pulled = await rectOf(page, dlg);

      expect(rest.y - pulled.y < 60, `${tag}: no resistance when pulling up (${rest.y - pulled.y} px)`);
      await pull.release();
      await page.waitForTimeout(700);
      // far drag closes (clean form: no question)
      const far = await touchSwipe(page, [195, rest.y + 10], [195, rest.y + 300], { steps: 8 });

      await far.release();
      await page.waitForTimeout(900);
      expect((await count(page, dlg)) === 0, `${tag}: far swipe did not close the sheet`);
      await open();
      await page.keyboard.press("Escape");
      await page.waitForTimeout(600);
      expect((await count(page, dlg)) === 0, `${tag}: Esc did not close a clean sheet`);
      // dirty: swipe, Esc and backdrop ask first
      await open();
      await page.getByLabel(/ФИО/).first().click();
      await page.keyboard.type("Тест");
      const fast = await touchSwipe(page, [195, rest.y + 10], [195, rest.y + 300], { steps: 8 });

      await fast.release();
      await page.waitForTimeout(900);
      expect(await ask.isVisible(), `${tag}: swipe on a dirty form did not ask`);
      expect((await count(page, dlg)) === 2, `${tag}: the form closed under the question`);
      await page.getByRole("button", { name: "Продолжить" }).click();
      await page.waitForTimeout(600);
      expect((await count(page, dlg)) === 1, `${tag}: «Продолжить» did not keep the form`);
      const afterAsk = await rectOf(page, dlg);

      expect(Math.abs(afterAsk.y - rest.y) < 2, `${tag}: sheet did not return after the question (${afterAsk.y})`);
      await page.touchscreen.tap(195, 60); // backdrop
      await page.waitForTimeout(500);
      expect(await ask.isVisible(), `${tag}: backdrop on a dirty form did not ask`);
      await page.getByRole("button", { name: "Продолжить" }).click();
      await page.waitForTimeout(500);
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
      expect(await ask.isVisible(), `${tag}: Esc on a dirty form did not ask`);
      await page.getByRole("button", { name: "Закрыть без сохранения" }).click();
      await page.waitForTimeout(900);
      expect((await count(page, dlg)) === 0, `${tag}: «Закрыть без сохранения» did not close`);
      await open();
      await page.keyboard.press("Escape");
      await page.waitForTimeout(600);
      expect((await count(page, dlg)) === 0, `${tag}: the guard stayed on after the form was discarded`);
      console.log(`${tag.padEnd(28)} phone sheet: follows finger, springs back, rubber band, closes; dirty guard on swipe / backdrop / Esc`);
      await context.close();
    }

    // -- row menus: the «…» popover closes before a (lazy) modal opens and leaves nothing behind
    for (const vp of [DESKTOP, PHONE]) {
      for (const path of ["/leads", "/users", "/rooms"]) {
        const context = await loggedIn(mode, vp);
        const page = await goto(context, mode, path);
        const trigger = page.locator('main button[aria-label^="Действия"]:visible').first();

        if (!(await trigger.count())) {
          if (path === "/leads") bad.push(`${tag}: no row menu found on ${path}, the check proves nothing`);
          await context.close();
          continue;
        }
        await trigger.click();
        await page.getByRole("menuitem").first().waitFor();
        // the modal chunk arrives late (a slow network): the menu must not wait for it to close
        await page.route("**/_next/static/**", async (route) => {
          await new Promise((r) => setTimeout(r, 700));
          await route.continue();
        });
        await (path === "/leads" && vp === DESKTOP ? page.getByRole("menuitem", { name: "Изменить" }) : page.getByRole("menuitem")).first().click({ force: true });
        await page.waitForTimeout(2600);
        const menus = await count(page, '[role="menu"]');
        const dialogs = await count(page, '[role="dialog"]');

        expect(menus === 0, `${tag}: row menu left open on ${path} ${vp.width}px (${menus})`);
        expect(dialogs <= 1, `${tag}: stale dialog on ${path} ${vp.width}px (${dialogs})`);
        await page.keyboard.press("Escape");
        await page.waitForTimeout(700);
        expect((await count(page, '[role="menu"]')) === 0 && (await count(page, '[role="dialog"]')) === 0, `${tag}: leftovers after closing on ${path} ${vp.width}px`);
        await context.close();
      }
    }

    // -- a touch tap on the thin backdrop strip above a near-full-height sheet closes it (asks when dirty)
    {
      const context = await loggedIn(mode, { width: 390, height: 440 });
      const page = await goto(context, mode, "/students");
      const dlg = '[role="dialog"]';

      await page.getByRole("button", { name: /Студент/ }).first().click();
      await page.locator(dlg).first().waitFor();
      await page.waitForTimeout(800);
      const r = await rectOf(page, dlg);

      expect(r.y > 0 && r.y < 24, `${tag}: sheet is not near full height here (${r.y})`);
      await page.touchscreen.tap(195, r.y / 2);
      await page.waitForTimeout(700);
      expect((await count(page, dlg)) === 0, `${tag}: touch on the backdrop strip did not close the sheet`);
      expect(new URL(page.url()).pathname === "/students", `${tag}: the backdrop tap went through to the page (${page.url()})`);
      await page.goto(`${BASE}/students`, { waitUntil: "networkidle" });
      await page.getByRole("button", { name: /Студент/ }).first().click();
      await page.locator(dlg).first().waitFor();
      await page.waitForTimeout(800);
      await page.getByLabel(/ФИО/).first().click();
      await page.keyboard.type("Тест");
      await page.touchscreen.tap(195, r.y / 2);
      await page.waitForTimeout(500);
      expect(await page.getByText("Закрыть без сохранения?").isVisible(), `${tag}: touch on the backdrop strip of a dirty form did not ask`);
      await context.close();
    }

    // -- desktop: centred modal, guard on Esc and backdrop
    {
      const context = await loggedIn(mode, DESKTOP);
      const page = await goto(context, mode, "/students");
      const dlg = '[role="dialog"]';

      await page.getByRole("button", { name: /Студент/ }).first().click();
      await page.locator(dlg).first().waitFor();
      await page.waitForTimeout(600);
      const r = await rectOf(page, dlg);

      expect(r.y > 20 && r.y + r.h < 880 && r.x > 100, `${tag}: desktop modal is not centred (${JSON.stringify(r)})`);
      await page.getByLabel(/ФИО/).first().click();
      await page.keyboard.type("Тест");
      await page.keyboard.press("Escape");
      await page.waitForTimeout(400);
      expect(await page.getByText("Закрыть без сохранения?").isVisible(), `${tag}: desktop Esc on a dirty form did not ask`);
      await page.getByRole("button", { name: "Продолжить" }).click();
      await page.waitForTimeout(400);
      await page.mouse.click(20, 450);
      await page.waitForTimeout(400);
      expect(await page.getByText("Закрыть без сохранения?").isVisible(), `${tag}: desktop backdrop on a dirty form did not ask`);
      console.log(`${tag.padEnd(28)} desktop modal: centred, guard on Esc / backdrop`);
      await context.close();
    }
  }
}
await browser.close();

if (bad.length) {
  console.error(`FAIL:\n  ${bad.join("\n  ")}`);
  process.exit(1);
}
console.log("OK: public pages visible; overlays move normally and stand still under reduced motion");
