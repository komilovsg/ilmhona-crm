import assert from "node:assert/strict";
import { test } from "node:test";

import { fitSteps, pickFit } from "./fit.ts";
import { fontFaceCss, fontFile, nearestWeight } from "./fonts.ts";
import { domToRuns, normalizeRuns, resolveRuns, runsToHtml, type NodeLike } from "./runs.ts";

const text = (t: string): NodeLike => ({ nodeType: 3, nodeName: "#text", textContent: t, childNodes: [] });
const el = (name: string, attrs: Record<string, string> = {}, kids: NodeLike[] = []): NodeLike => ({
  nodeType: 1,
  nodeName: name,
  textContent: kids.map((k) => k.textContent).join(""),
  childNodes: kids,
  getAttribute: (n) => attrs[n] ?? null,
});

test("DOM with chips, text and line breaks becomes runs", () => {
  const root = el("DIV", {}, [text("Выдан "), el("SPAN", { "data-field": "student.full_name" }, [text("ФИО")]), el("BR"), text("за курс "), el("SPAN", { "data-field": "certificate.issued_date", "data-format": "d month yyyy" }), el("BR", { "data-pad": "1" })]);

  assert.deepEqual(domToRuns(root), [
    { text: "Выдан " },
    { field: "student.full_name" },
    { text: "\nза курс " },
    { field: "certificate.issued_date", format: "d month yyyy" },
  ]);
});

test("gender chip and browser-made blocks", () => {
  const root = el("DIV", {}, [el("DIV", {}, [text("one")]), el("DIV", {}, [text("two "), el("SPAN", { "data-male": "прошёл", "data-female": "прошла" })])]);

  assert.deepEqual(domToRuns(root), [{ text: "one\ntwo " }, { gender: { male: "прошёл", female: "прошла" } }]);
});

test("a deleted chip is simply absent; empty text vanishes", () => {
  assert.deepEqual(domToRuns(el("DIV", {}, [text(""), text("a"), text("b")])), [{ text: "ab" }]);
  assert.deepEqual(normalizeRuns([{ text: "" }, { text: "x" }, { text: "y" }, { field: "f" }]), [{ text: "xy" }, { field: "f" }]);
});

test("runs to html escapes text, makes chips non-editable, pads a trailing break", () => {
  const html = runsToHtml([{ text: "a<b\n" }, { field: "course.name" }, { gender: { male: "m", female: "f" } }, { text: "\n" }], () => "Курс");

  assert.match(html, /a&lt;b<br>/);
  assert.match(html, /contenteditable="false" data-field="course.name">Курс</);
  assert.match(html, /data-male="m" data-female="f"/);
  assert.ok(html.endsWith('<br><br data-pad="1">'));
  assert.equal(runsToHtml([], () => ""), '<br data-pad="1">');
});

test("sample values and gender pick", () => {
  const runs = [{ text: "№ " }, { field: "certificate.number" }, { text: " " }, { gender: { male: "он", female: "она" } }];

  assert.equal(resolveRuns(runs, { "certificate.number": "C-1" }, "female"), "№ C-1 она");
  assert.equal(resolveRuns(runs, {}, "male"), "№  он");
});

test("font files and css", () => {
  assert.equal(fontFile("Montserrat", 700, true), "Montserrat-700Italic.ttf");
  assert.equal(fontFile("Montserrat", 400, false), "Montserrat-400.ttf");
  const css = fontFaceCss([{ family: "Montserrat", weights: [400, 700], italic_weights: [400] }]);

  assert.equal(css.split("@font-face").length - 1, 3);
  assert.match(css, /Montserrat-400Italic\.ttf/);
  assert.deepEqual(nearestWeight({ family: "M", weights: [400, 700], italic_weights: [] }, 600, true), { weight: 700, italic: false });
});

test("shrink-to-fit steps by 0.5 pt down to the minimum", () => {
  assert.deepEqual(fitSteps(12, 10), [12, 11.5, 11, 10.5, 10]);
  assert.deepEqual(fitSteps(12, null), [12]);
  assert.deepEqual(fitSteps(12, 12), [12]);
  assert.deepEqual(pickFit(fitSteps(12, 10), (pt) => pt <= 11), { pt: 11, overflow: false });
  assert.deepEqual(pickFit(fitSteps(12, 10), () => false), { pt: 10, overflow: true });
});
