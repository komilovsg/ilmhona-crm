import assert from "node:assert/strict";
import { test } from "node:test";

import {
  apiRequestHeaders,
  CLIENT_IP_HEADER,
  CLIENT_UA_HEADER,
  PROXY_SECRET_HEADER,
  trustedClientIp,
} from "./forward.ts";

test("adds the server secret and drops one the browser sent", () => {
  const incoming = new Headers({ [PROXY_SECRET_HEADER]: "forged", cookie: "a=1" });
  const out = apiRequestHeaders(incoming, "", " real-secret ");
  assert.equal(out.get(PROXY_SECRET_HEADER), "real-secret");
  assert.equal(out.get("cookie"), "a=1");
});

test("without a secret no header leaves, not even a forged one", () => {
  const out = apiRequestHeaders(new Headers({ [PROXY_SECRET_HEADER]: "forged" }), "", undefined);
  assert.equal(out.has(PROXY_SECRET_HEADER), false);
});

test("strips browser forwarding headers and forwards only the derived client ip", () => {
  const incoming = new Headers({
    "x-forwarded-for": "6.6.6.6",
    forwarded: "for=6.6.6.6",
    "x-real-ip": "6.6.6.6",
    "x-vercel-forwarded-for": "6.6.6.6",
    [CLIENT_IP_HEADER]: "6.6.6.6",
  });
  const out = apiRequestHeaders(incoming, "203.0.113.9", "secret");
  assert.equal(out.get(CLIENT_IP_HEADER), "203.0.113.9");
  assert.equal(out.has("x-forwarded-for"), false);
  assert.equal(out.has("forwarded"), false);
  assert.equal(out.has("x-real-ip"), false);
  assert.equal(out.has("x-vercel-forwarded-for"), false);
});

test("no client-ip header is set when none could be derived", () => {
  const out = apiRequestHeaders(new Headers({ "x-forwarded-for": "6.6.6.6" }), "", "secret");
  assert.equal(out.has(CLIENT_IP_HEADER), false);
});

test("trusts Vercel's own header, never the spoofable x-forwarded-for", () => {
  assert.equal(
    trustedClientIp(new Headers({ "x-forwarded-for": "6.6.6.6", "x-vercel-forwarded-for": "203.0.113.9" })),
    "203.0.113.9",
  );
  assert.equal(trustedClientIp(new Headers({ "x-real-ip": "198.51.100.4" })), "198.51.100.4");
  assert.equal(trustedClientIp(new Headers({ "x-forwarded-for": "6.6.6.6" })), "");
});

test("forwards the browser User-Agent in its own header, capped, never a forged one", () => {
  const incoming = new Headers({ "user-agent": "Chrome/130 " + "x".repeat(600), [CLIENT_UA_HEADER]: "forged" });
  const out = apiRequestHeaders(incoming, "", "secret");
  assert.equal(out.get(CLIENT_UA_HEADER)?.length, 400);
  assert.ok(out.get(CLIENT_UA_HEADER)?.startsWith("Chrome/130"));
  assert.equal(apiRequestHeaders(new Headers({ [CLIENT_UA_HEADER]: "forged" }), "", "s").has(CLIENT_UA_HEADER), false);
});
