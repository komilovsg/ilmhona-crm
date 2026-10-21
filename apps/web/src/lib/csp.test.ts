import assert from "node:assert/strict";
import { test } from "node:test";

import { buildCsp, makeNonce } from "./csp.ts";

function directives(csp: string): Map<string, string> {
  return new Map(
    csp.split(";").map((d) => {
      const [name, ...rest] = d.trim().split(/\s+/);
      return [name, rest.join(" ")];
    }),
  );
}

test("script-src is nonce-locked with strict-dynamic and no unsafe-inline", () => {
  const d = directives(buildCsp("abc123", { dev: false }));
  const script = d.get("script-src") ?? "";
  assert.match(script, /'nonce-abc123'/);
  assert.match(script, /'strict-dynamic'/);
  assert.doesNotMatch(script, /'unsafe-inline'/);
  assert.doesNotMatch(script, /'unsafe-eval'/); // prod has no eval
});

test("clickjacking and injection sinks are closed", () => {
  const d = directives(buildCsp("n", { dev: false }));
  assert.equal(d.get("frame-ancestors"), "'none'");
  assert.equal(d.get("object-src"), "'none'");
  assert.equal(d.get("base-uri"), "'self'");
  assert.equal(d.get("form-action"), "'self'");
  assert.equal(d.get("default-src"), "'self'");
});

test("inline styles stay allowed (HeroUI / framer-motion) but connect-src is same-origin", () => {
  const d = directives(buildCsp("n", { dev: false }));
  assert.match(d.get("style-src") ?? "", /'unsafe-inline'/);
  assert.equal(d.get("connect-src"), "'self'");
});

test("production upgrades insecure requests; dev relaxes for HMR only", () => {
  const prod = directives(buildCsp("n", { dev: false }));
  assert.ok(prod.has("upgrade-insecure-requests"));
  const dev = directives(buildCsp("n", { dev: true }));
  assert.ok(!dev.has("upgrade-insecure-requests"));
  assert.match(dev.get("script-src") ?? "", /'unsafe-eval'/);
  assert.match(dev.get("connect-src") ?? "", /ws:/);
});

test("nonce is random and non-empty", () => {
  assert.notEqual(makeNonce(), makeNonce());
  assert.ok(makeNonce().length > 0);
});
