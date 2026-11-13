import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

// Next.js 16.0.0-16.4.0 has unauthenticated remote code execution (GHSA-2464-fhr4-w9xw image
// optimizer, GHSA-673q-mjm6-r5xr `use cache`) and an App Router DoS (GHSA-p3m5-59mp-jv5r).
const FIRST_PATCHED = [16, 4, 1];

function parts(version: string): number[] {
  return version.split("-")[0].split(".").map(Number);
}

function atLeast(have: number[], need: number[]): boolean {
  for (let i = 0; i < need.length; i++) {
    if (have[i] !== need[i]) return have[i] > need[i];
  }
  return true;
}

test("installed next is past the 16.4.0 remote code execution advisories", () => {
  const require = createRequire(import.meta.url);
  const pkg = JSON.parse(readFileSync(require.resolve("next/package.json"), "utf8")) as { version: string };
  assert.ok(atLeast(parts(pkg.version), FIRST_PATCHED), `next ${pkg.version} is vulnerable`);
});

test("package.json pins a patched next", () => {
  const own = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8")) as {
    dependencies: Record<string, string>;
  };
  assert.ok(atLeast(parts(own.dependencies.next.replace(/^[\^~]/, "")), FIRST_PATCHED));
});
