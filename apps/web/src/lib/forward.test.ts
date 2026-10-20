import assert from "node:assert/strict";
import { test } from "node:test";

import { apiRequestHeaders, PROXY_SECRET_HEADER } from "./forward.ts";

test("adds the server secret and drops one the browser sent", () => {
  const incoming = new Headers({ [PROXY_SECRET_HEADER]: "forged", cookie: "a=1" });
  const out = apiRequestHeaders(incoming, " real-secret ");
  assert.equal(out.get(PROXY_SECRET_HEADER), "real-secret");
  assert.equal(out.get("cookie"), "a=1");
});

test("without a secret no header leaves, not even a forged one", () => {
  const out = apiRequestHeaders(new Headers({ [PROXY_SECRET_HEADER]: "forged" }), undefined);
  assert.equal(out.has(PROXY_SECRET_HEADER), false);
});
