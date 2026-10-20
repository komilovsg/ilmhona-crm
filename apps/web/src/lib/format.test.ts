import assert from "node:assert/strict";
import { test } from "node:test";

import { telHref } from "./format.ts";

test("tel: hrefs have no spaces or punctuation", () => {
  assert.equal(telHref("+992 900 12-34-56"), "tel:+992900123456");
  assert.equal(telHref("900 12 34 56"), "tel:+992900123456");
  assert.equal(telHref("992900123456"), "tel:+992900123456");
  assert.equal(telHref("+992 (900) 123456"), "tel:+992900123456");
});
