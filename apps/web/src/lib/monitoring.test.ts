import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { pathOnly, scrubBreadcrumb, scrubEvent, scrubText } from "./monitoring.ts";

test("phones and e-mails inside text are replaced", () => {
  for (const phone of ["+992900000000", "+992 (90) 000-00-00", "900000000", "90.000.00.00"]) {
    assert.equal(scrubText(`call ${phone} now`), "call [Filtered] now");
  }
  assert.equal(scrubText("order 12345 ok"), "order 12345 ok");
  assert.equal(scrubText("a.b+c@d-e.example.test"), "[Filtered]");
});

test("urls keep the path only", () => {
  assert.equal(pathOnly("https://x.test/api/v1/students?phone=%2B992900000000#a"), "https://x.test/api/v1/students");
  assert.equal(pathOnly("/api/v1/users?q=Test"), "/api/v1/users");
});

test("an event carries no personal data", () => {
  const event = {
    event_id: "0123456789abcdef0123456789abcdef",
    timestamp: 1760000000.123,
    request: {
      method: "POST",
      url: "https://x.test/students?phone=%2B992900000000",
      query_string: "phone=%2B992900000000&q=Test",
      data: { name: "Test Person" },
      cookies: { ilm_access: "secret-token" },
      headers: { Cookie: "ilm_access=secret-token", "X-Client-Ip": "203.0.113.5", "User-Agent": "UA/1.0" },
    },
    user: { id: "u-1", email: "person@example.test", ip_address: "1.1.1.1" },
    extra: { name: "Test Person" },
    breadcrumbs: [
      { category: "console", message: "Test Person" },
      { category: "fetch", data: { url: "/api/v1/students?q=Test+Person", method: "GET", status_code: 200 } },
      { category: "ui.input", message: "input value Test Person", data: { value: "x" } },
    ],
    exception: { values: [{ type: "Error", value: "failed for person@example.test +992 90 000 0000" }] },
  };
  const out = scrubEvent(event) as typeof event;
  const dump = JSON.stringify(out);
  for (const leaked of ["992", "person@example.test", "secret-token", "203.0.113.5", "1.1.1.1", "q=Test"]) {
    assert.ok(!dump.includes(leaked), leaked);
  }
  assert.deepEqual(out.user, { id: "u-1" });
  assert.deepEqual(out.request.headers, { "User-Agent": "UA/1.0" });
  assert.equal(out.request.url, "https://x.test/students");
  assert.equal(out.request.query_string, "phone=[Filtered]&q=[Filtered]");
  assert.equal(out.breadcrumbs.length, 2);
  assert.equal(out.event_id, event.event_id);
  assert.equal(out.timestamp, event.timestamp);
});

test("breadcrumbs: no console, no input values", () => {
  assert.equal(scrubBreadcrumb({ category: "console", message: "x" }), null);
  const crumb = scrubBreadcrumb({ category: "ui.click", message: "button", data: { value: "secret" } });
  assert.ok(crumb && !("data" in crumb));
});

test("browser code never imports the whole SDK namespace (that bundles Session Replay)", () => {
  const src = new URL("../", import.meta.url);
  for (const file of ["instrumentation-client.ts", "lib/report-error.ts", "lib/sentry-browser.ts"]) {
    const code = readFileSync(new URL(file, src), "utf8").replace(/^\s*(\/\/|\*|\/\*\*).*$/gm, "");
    assert.ok(!/import\(\s*["']@sentry\/nextjs["']\s*\)|import \* as/.test(code), file);
    assert.ok(!/replay|feedback/i.test(code), file);
  }
});

test("names (Cyrillic, also percent-encoded) and URL queries anywhere are removed", () => {
  const event = {
    type: "transaction",
    transaction: "/students",
    exception: { values: [{ type: "TypeError", value: "no tariff for Раҳимов Фирӯз (Иванова Мария)" }] },
    contexts: {
      trace: { data: { "http.query": "?search=Rahimov", "url.full": "https://x.test/students?search=Rahimov&p=2" } },
      nextjs: { request_path: "/students/%D0%98%D0%B2%D0%B0%D0%BD/edit?q=Rahimov" },
    },
    spans: [
      {
        description: "GET /api/v1/students?search=Rahimov&branch=1",
        data: { url: "/api/v1/students?search=Rahimov", "http.query": "search=Rahimov" },
      },
      { description: "GET https://x.test/api/v1/students/%D0%A8%D0%B0%D1%80%D0%B8%D0%BF%D0%BE%D0%B2" },
    ],
    breadcrumbs: [{ category: "sentry.event", message: "Error: student Шарипов Ҷамшед not found" }],
  };
  const dump = JSON.stringify(scrubEvent(event));
  for (const leaked of ["Rahimov", "Раҳимов", "Фирӯз", "Иванова", "Мария", "Шарипов", "Ҷамшед", "%D0", "%D1"]) {
    assert.ok(!dump.includes(leaked), leaked);
  }
  assert.ok(dump.includes("GET /api/v1/students"), "the path stays");
  assert.ok(dump.includes("no tariff for"), "the English text stays");
});
