import assert from "node:assert/strict";
import { test } from "node:test";

import { ERROR_COPY, errorCode } from "./error-copy.ts";

const CYRILLIC = /[А-Яа-яЁё]/;

test("every error screen string is Russian", () => {
  for (const screen of Object.values(ERROR_COPY)) {
    for (const [key, value] of Object.entries(screen)) {
      if (key === "code") continue;
      assert.match(value, CYRILLIC, `${key}: ${value}`);
    }
  }
});

test("404 screen names the page and offers home and back", () => {
  assert.equal(ERROR_COPY.notFound.code, "404");
  assert.equal(ERROR_COPY.notFound.title, "Страница не найдена");
  assert.equal(ERROR_COPY.notFound.home, "На главную");
  assert.equal(ERROR_COPY.notFound.back, "Назад");
});

test("error screen offers retry and home", () => {
  assert.equal(ERROR_COPY.failure.title, "Что-то пошло не так");
  assert.equal(ERROR_COPY.failure.retry, "Повторить");
  assert.equal(ERROR_COPY.failure.home, "На главную");
});

test("the support code is the digest only, never the message", () => {
  assert.equal(errorCode({ digest: "1234567" }), "1234567");
  assert.equal(errorCode({ digest: " " }), null);
  assert.equal(errorCode(new Error("secret stack detail")), null);
  assert.equal(errorCode(null), null);
});
