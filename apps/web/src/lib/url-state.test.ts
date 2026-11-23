import assert from "node:assert/strict";
import { test } from "node:test";

import { readPage, readState, writePage, writeState } from "./url-state.ts";

const NONE = { q: "", status: null as string | null, review: false };

test("filters are read from the address", () => {
  assert.deepEqual(readState("", NONE), NONE);
  assert.deepEqual(readState("?q=python&status=активный&review=1&page=3", NONE), {
    q: "python",
    status: "активный",
    review: true,
  });
  assert.deepEqual(readState("?tab=grades", NONE), NONE);
});

test("a default value leaves the address", () => {
  assert.equal(writeState("", NONE, { q: "python" }), "q=python");
  assert.equal(writeState("q=python&status=x&review=1", NONE, { q: "", status: null, review: false }), "");
  assert.equal(writeState("q=a", NONE, { review: true }), "q=a&review=1");
});

test("other parameters survive a filter change", () => {
  assert.equal(writeState("tab=debtors&page=2", NONE, { q: "x" }), "tab=debtors&page=2&q=x");
  assert.equal(writeState("q=a", NONE, { tab: "x" } as never), "q=a");
});

test("what was written is read back", () => {
  const next = { q: "Алиев & co", status: "набор", review: true };

  assert.deepEqual(readState(writeState("", NONE, next), NONE), next);
});

test("the page number", () => {
  assert.equal(readPage(""), 1);
  assert.equal(readPage("?page=4"), 4);
  assert.equal(readPage("?page=0"), 1);
  assert.equal(readPage("?page=abc"), 1);
  assert.equal(writePage("q=a", 3), "q=a&page=3");
  assert.equal(writePage("q=a&page=3", 1), "q=a");
});
