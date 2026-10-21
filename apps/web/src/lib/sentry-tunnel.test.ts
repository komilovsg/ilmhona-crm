import assert from "node:assert/strict";
import { test } from "node:test";

import { allowed, MAX_ENVELOPE_BYTES, readCapped, tunnelTarget } from "./sentry-tunnel.ts";

const DSN = "https://abc123@o42.ingest.de.sentry.io/4510";
const envelope = (dsn: string) => `${JSON.stringify({ dsn, event_id: "x" })}\n{"type":"event"}\n{}`;

test("forwards only envelopes naming our DSN, to our host", () => {
  assert.equal(tunnelTarget(envelope(DSN), DSN), "https://o42.ingest.de.sentry.io/api/4510/envelope/");
  assert.equal(tunnelTarget(envelope("https://abc123@evil.example/4510"), DSN), null);
  assert.equal(tunnelTarget(envelope("https://abc123@o42.ingest.de.sentry.io/9999"), DSN), null);
  assert.equal(tunnelTarget("not json\n{}", DSN), null);
  assert.equal(tunnelTarget(envelope(DSN), undefined), null);
  // even a misconfigured DSN pointing outside sentry.io is never forwarded to
  assert.equal(tunnelTarget(envelope("https://k@evil.example/1"), "https://k@evil.example/1"), null);
});

test("the body is read up to the byte cap, with or without a content-length", async () => {
  const post = (body: BodyInit, headers: HeadersInit = {}) =>
    new Request("http://x.test/monitoring", { method: "POST", body, headers, duplex: "half" } as RequestInit);
  assert.equal(await readCapped(post("ok\n{}")), "ok\n{}");
  // 150 000 Cyrillic letters = 300 000 bytes: over the cap although the string is shorter
  assert.equal(await readCapped(post("ж".repeat(150_000))), null);
  // streamed (chunked, no content-length): never buffered past the cap
  let pulled = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(c) {
      pulled += 1;
      if (pulled > 1000) c.close();
      else c.enqueue(new Uint8Array(64_000));
    },
  });
  assert.equal(await readCapped(post(stream)), null);
  assert.ok(pulled < 10, `read ${pulled} chunks`);
  assert.equal(await readCapped(post("x", { "content-length": String(MAX_ENVELOPE_BYTES + 1) })), null);
});

test("rate limit per address", () => {
  const t = 1_000_000;
  for (let i = 0; i < 30; i++) assert.ok(allowed("1.1.1.1", t));
  assert.equal(allowed("1.1.1.1", t), false);
  assert.ok(allowed("2.2.2.2", t));
  assert.ok(allowed("1.1.1.1", t + 61_000));
});
