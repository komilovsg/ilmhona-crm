import assert from "node:assert/strict";
import { test } from "node:test";

import { overBy, overToast, overWarning, wouldExceed } from "./capacity.ts";

test("soft capacity helpers", () => {
  assert.equal(wouldExceed({ enrolled: 19, capacity: 20 }), false);
  assert.equal(wouldExceed({ enrolled: 20, capacity: 20 }), true);
  assert.equal(wouldExceed(undefined), false);
  assert.equal(overBy({ enrolled: 22, capacity: 20 }), 2);
  assert.equal(overBy({ enrolled: 5, capacity: 20 }), 0);
  assert.equal(overWarning({ enrolled: 20, capacity: 20 }), "Сверх плана: будет 21 из 20. Записать всё равно?");
  assert.equal(overToast({ enrolled: 21, capacity: 20 }), ", сверх плана: 21 из 20");
  assert.equal(overToast(null), "");
});
