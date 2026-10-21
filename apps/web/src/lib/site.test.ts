import assert from "node:assert/strict";
import { test } from "node:test";

import { loginMetadata, siteMetadata, siteViewport } from "./site.ts";

test("root metadata has the Open Graph card and stays noindex", () => {
  const og = siteMetadata.openGraph as { title: string; type: string; locale: string; images: { url: string }[] };
  assert.equal(og.title, "ilmhona CRM");
  assert.equal(og.type, "website");
  assert.equal(og.locale, "ru_RU");
  assert.equal(og.images[0].url, "/opengraph-image");
  assert.equal((siteMetadata.twitter as { card: string }).card, "summary_large_image");
  assert.deepEqual(siteMetadata.robots, { index: false, follow: false });
  assert.equal(String(siteMetadata.metadataBase), "https://ilmhona-crm.vercel.app/");
  assert.equal(Array.isArray(siteViewport.themeColor), true);
});

test("the login page carries the same card", () => {
  assert.deepEqual(loginMetadata.title, { absolute: "ilmhona CRM" });
  assert.equal((loginMetadata.openGraph as { url: string }).url, "/login");
  assert.ok((loginMetadata.openGraph as { images: unknown[] }).images.length > 0);
});
