import assert from "node:assert/strict";
import { test } from "node:test";

import { singleFlight } from "./submit.ts";

test("two submits in the same tick send exactly one request", async () => {
  let calls = 0;
  const submit = singleFlight(async () => {
    calls++;
    await new Promise((r) => setTimeout(r, 5));
  });

  await Promise.all([submit(), submit()]);
  assert.equal(calls, 1);
  await submit(); // free again after the request ends
  assert.equal(calls, 2);
});

test("a failed request frees the guard", async () => {
  let calls = 0;
  const submit = singleFlight(async () => {
    calls++;
    throw new Error("boom");
  });

  await submit();
  await submit();
  assert.equal(calls, 2);
});
