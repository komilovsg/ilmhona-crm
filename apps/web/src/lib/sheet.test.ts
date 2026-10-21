import assert from "node:assert/strict";
import { test } from "node:test";

import { dismissAction, isEditField, rubberband, sheetOffset, shouldCloseSheet, toastSwipe, velocityOf } from "./sheet.ts";

const H = 600;

test("a sheet follows the finger down 1:1 and resists upwards", () => {
  assert.equal(sheetOffset(120, H), 120);
  const up = sheetOffset(-100, H);

  assert.ok(up < 0 && up > -100 * 0.55, `rubber-banded, got ${up}`);
  assert.ok(sheetOffset(-400, H) > -160, "never runs away");
  assert.ok(rubberband(200, H) < rubberband(100, H) * 2, "resistance grows");
});

test("a sheet closes on distance or on a fast downward flick, not on a small slow drag", () => {
  assert.equal(shouldCloseSheet({ offset: 80, velocity: 0, height: H }), false);
  assert.equal(shouldCloseSheet({ offset: 220, velocity: 0, height: H }), true);
  assert.equal(shouldCloseSheet({ offset: 40, velocity: 900, height: H }), true);
  assert.equal(shouldCloseSheet({ offset: 10, velocity: 900, height: H }), false, "a twitch is not a flick");
  assert.equal(shouldCloseSheet({ offset: 300, velocity: -400, height: H }), false, "flicking back up cancels");
  assert.equal(shouldCloseSheet({ offset: -20, velocity: 900, height: H }), false);
});

test("a toast is swiped away upwards or sideways, never by a tap or a downward drag", () => {
  assert.equal(toastSwipe({ dx: 0, dy: 0, vx: 0, vy: 0 }), null, "tap");
  assert.equal(toastSwipe({ dx: 3, dy: -12, vx: 0, vy: -100 }), null, "small slow move");
  assert.equal(toastSwipe({ dx: 0, dy: -50, vx: 0, vy: 0 }), "up");
  assert.equal(toastSwipe({ dx: 0, dy: -20, vx: 0, vy: -800 }), "up", "fast flick");
  assert.equal(toastSwipe({ dx: 120, dy: 4, vx: 0, vy: 0 }), "right");
  assert.equal(toastSwipe({ dx: -40, dy: 0, vx: -900, vy: 0 }), "left");
  assert.equal(toastSwipe({ dx: 0, dy: 90, vx: 0, vy: 900 }), null, "down");
});

test("release velocity uses the last 100 ms only", () => {
  const s = [
    { y: 0, t: 0 },
    { y: 5, t: 300 },
    { y: 20, t: 350 },
    { y: 70, t: 400 },
  ];

  assert.equal(velocityOf(s), 1000);
  assert.equal(velocityOf([]), 0);
  assert.equal(velocityOf([{ y: 5, t: 10 }]), 0);
});

test("dirty guard: an edited form asks before Esc / backdrop / swipe closes it", () => {
  assert.equal(dismissAction({ dirty: false }), "close");
  assert.equal(dismissAction({ dirty: true }), "confirm");
  assert.equal(dismissAction({ dirty: true, guarded: false }), "close", "a confirm or a finished wizard is never guarded");
});

test("only real edits make a form dirty", () => {
  assert.equal(isEditField({ tagName: "INPUT", type: "text" }), true);
  assert.equal(isEditField({ tagName: "INPUT", type: "checkbox" }), true);
  assert.equal(isEditField({ tagName: "TEXTAREA" }), true);
  assert.equal(isEditField({ tagName: "SELECT" }), true);
  assert.equal(isEditField({ tagName: "INPUT", type: "text", readOnly: true }), false);
  assert.equal(isEditField({ tagName: "INPUT", type: "search" }), false);
  assert.equal(isEditField({ tagName: "BUTTON" }), false);
  assert.equal(isEditField(null), false);
});
