import assert from "node:assert/strict";
import { test } from "node:test";

import { tourEnd, tourSeen } from "./tour.ts";

const store = new Map<string, string>();
(globalThis as { window?: unknown }).window = {
  localStorage: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  },
};

test("leaving mid-tour does not mark it seen", () => {
  const end = tourEnd("u1");
  end.leave();
  end.onDestroyed();
  assert.equal(tourSeen("u1"), false);
});

test("skip, close or finish marks it seen", () => {
  tourEnd("u2").onDestroyed();
  assert.equal(tourSeen("u2"), true);
});
