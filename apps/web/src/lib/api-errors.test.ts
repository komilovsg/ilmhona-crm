import assert from "node:assert/strict";
import { test } from "node:test";

import { errorText, fieldText } from "./api-errors.ts";

test("busy messages show the day as dd.mm.yyyy", () => {
  const params = { cohort: "G-1", date: "2026-11-17", start: "10:00", end: "11:30" };

  assert.equal(errorText("room_busy", params), "Аудитория занята потоком G-1: 17.11.2026, 10:00–11:30.");
  assert.equal(
    errorText("instructor_busy", params),
    "Инструктор в это время ведёт урок: поток G-1, 17.11.2026, 10:00–11:30.",
  );
});

test("field hints name the limit", () => {
  assert.equal(fieldText("missing"), "Обязательное поле");
  assert.equal(fieldText("string_too_long", { max_length: 200 }), "Не длиннее 200 символов");
  assert.equal(fieldText("string_too_short", { min_length: 1 }), "Заполните поле");
  assert.equal(fieldText("invalid_phone"), "Неверный номер. Пример: +992 90 123 45 67");
  assert.equal(fieldText("decimal_parsing"), "Введите число");
  assert.equal(fieldText("string_too_short", { min_length: 3 }), "Не короче 3 символов");
  assert.equal(fieldText("decimal_max_digits"), "Слишком большое число");
  assert.equal(fieldText("decimal_max_places"), "Слишком много знаков после запятой");
  assert.equal(fieldText("time_parsing"), "Неверное время");
  assert.equal(fieldText("date_from_datetime_parsing"), "Неверная дата");
  assert.equal(fieldText("int_parsing"), "Введите число");
  assert.equal(fieldText("greater_than_equal", { ge: 0 }), "Не меньше 0");
  assert.equal(fieldText("less_than_equal", { le: 100 }), "Не больше 100");
  assert.equal(fieldText("greater_than", { gt: 0 }), "Больше 0");
  assert.equal(fieldText("uuid_parsing"), "Выберите значение из списка");
  assert.equal(fieldText("literal_error"), "Выберите значение из списка");
  assert.equal(fieldText("date_from_datetime_parsing"), "Неверная дата");
  assert.equal(fieldText("value_error_email"), "Неверный email");
  assert.equal(fieldText("whatever"), "Неверное значение");
});
