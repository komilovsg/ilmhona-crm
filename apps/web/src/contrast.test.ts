import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { config } from "./hero.ts";

// WCAG 2.x contrast ratios of the brand tokens. Keeps white-on-primary and secondary text from regressing.
const channel = (hex: string, i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16);
const lin = (v: number) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const lum = (hex: string) => 0.2126 * lin(channel(hex, 0)) + 0.7152 * lin(channel(hex, 1)) + 0.0722 * lin(channel(hex, 2));
const ratio = (a: string, b: string) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);

  return (hi + 0.05) / (lo + 0.05);
};
/** `fg` at `alpha` over `bg` (Tailwind `bg-primary/10`). */
const over = (fg: string, bg: string, alpha: number) =>
  "#" +
  [0, 1, 2]
    .map((i) =>
      Math.round(channel(fg, i) * alpha + channel(bg, i) * (1 - alpha))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("");

const css = readFileSync(new URL("./app/globals.css", import.meta.url), "utf8");
const brandText = (selector: string) => css.match(new RegExp(`${selector}\\s*{[^}]*--brand-text:\\s*(#[0-9a-f]{6})`, "i"))![1];

for (const theme of ["light", "dark"] as const) {
  const c = config.themes![theme]!.colors as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const text = theme === "light" ? brandText(":root") : brandText("\\.dark");

  test(`${theme}: filled primary button text >= 4.5`, () => {
    assert.ok(ratio(c.primary.DEFAULT, c.primary.foreground) >= 4.5);
  });
  test(`${theme}: filled primary button is visible on page and cards (>= 3)`, () => {
    for (const bg of [c.background, c.content1]) assert.ok(ratio(c.primary.DEFAULT, bg) >= 3, bg);
  });
  test(`${theme}: secondary text (default-500, also the dash placeholder) >= 4.5`, () => {
    for (const bg of [c.background, c.content1]) assert.ok(ratio(c.default[500], bg) >= 4.5, bg);
  });
  test(`${theme}: text inside inputs (the «TJS» suffix, default-600 on default-100) >= 4.5`, () => {
    assert.ok(ratio(c.default[600], c.default[100]) >= 4.5);
  });
  test(`${theme}: brand text and selected state on tint >= 4.5`, () => {
    for (const bg of [c.background, c.content1, over(c.primary.DEFAULT, c.content1, 0.1), over(c.primary.DEFAULT, c.background, 0.1)]) {
      assert.ok(ratio(text, bg) >= 4.5, `${text} on ${bg}`);
    }
  });
  test(`${theme}: role chip user count (selected: brand text on tint, idle: foreground on card)`, () => {
    // roles/page.tsx: the count has no colour of its own, it inherits the chip's text colour
    assert.ok(ratio(c.foreground, c.content1) >= 4.5);
    assert.ok(ratio(text, over(c.primary.DEFAULT, c.content1, 0.1)) >= 4.5);
  });
}
