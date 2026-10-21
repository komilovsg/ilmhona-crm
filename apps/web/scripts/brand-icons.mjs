#!/usr/bin/env node
// Rebuilds every icon from public/brand/ilm-mark.svg (run `node scripts/brand-icons.mjs` after changing the mark).
// Needs `rsvg-convert` (brew install librsvg). Writes: src/app/icon.svg, favicon.ico, apple-icon.png,
// public/icon-192.png, icon-512.png, icon-maskable-192.png, icon-maskable-512.png.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const mark = readFileSync(join(root, "public/brand/ilm-mark.svg"), "utf8").match(/ d="([^"]+)"/)[1];
const W = 960;
const H = 754;
const DARK = "#101820";

/** The mark centred in a square `size` px tile; `frac` = mark width / tile width. */
function tile(size, frac, radius, withGradient = true) {
  const w = size * frac;
  const k = w / W;
  const x = (size - w) / 2;
  const y = (size - H * k) / 2;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
<defs><radialGradient id="g" gradientUnits="userSpaceOnUse" cx="${size * 0.05}" cy="${size * 0.12}" r="${size * 1.05}">
<stop offset="0" stop-color="#46d9f7"/><stop offset="0.3" stop-color="#2493b4"/><stop offset="0.72" stop-color="#14303d"/><stop offset="1" stop-color="${DARK}"/>
</radialGradient></defs>
${withGradient ? `<rect width="${size}" height="${size}" rx="${radius * size}" fill="url(#g)"/>` : ""}
<path fill="#fff" transform="translate(${x} ${y}) scale(${k})" d="${mark}"/></svg>`;
}

const tmp = mkdtempSync(join(tmpdir(), "ilm-icons-"));

function png(size, frac, radius) {
  const svgPath = join(tmp, `t${size}-${frac}.svg`);

  writeFileSync(svgPath, tile(size, frac, radius));

  return execFileSync("rsvg-convert", [svgPath]);
}

const out = (rel, data) => writeFileSync(join(root, rel), data);

// favicon.svg: the bare mark, dark on light tabs and white on dark tabs.
out(
  "src/app/icon.svg",
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}"><style>path{fill:${DARK}}@media (prefers-color-scheme:dark){path{fill:#fff}}</style><path d="${mark}"/></svg>\n`,
);

out("src/app/apple-icon.png", png(180, 0.6, 0));
out("public/icon-192.png", png(192, 0.6, 0.22));
out("public/icon-512.png", png(512, 0.6, 0.22));
// maskable: full bleed, the mark inside the 80 % safe zone
out("public/icon-maskable-192.png", png(192, 0.46, 0));
out("public/icon-maskable-512.png", png(512, 0.46, 0));

// favicon.ico: 16 / 32 / 48 PNG frames
const sizes = [16, 32, 48];
const frames = sizes.map((s) => png(s, 0.74, 0.2));
const head = Buffer.alloc(6 + 16 * sizes.length);

head.writeUInt16LE(0, 0);
head.writeUInt16LE(1, 2);
head.writeUInt16LE(sizes.length, 4);
let offset = head.length;

sizes.forEach((s, i) => {
  const o = 6 + 16 * i;

  head.writeUInt8(s, o);
  head.writeUInt8(s, o + 1);
  head.writeUInt16LE(1, o + 4);
  head.writeUInt16LE(32, o + 6);
  head.writeUInt32LE(frames[i].length, o + 8);
  head.writeUInt32LE(offset, o + 12);
  offset += frames[i].length;
});
out("src/app/favicon.ico", Buffer.concat([head, ...frames]));
console.log("icons written");
