// Text content of a certificate layer: runs <-> the editable DOM (field chips are non-editable spans).

import { formatDate } from "./dates.ts";
import type { Run } from "./types.ts";

/** The part of a DOM node the serialiser reads (so it can be unit-tested without a DOM). */
export type NodeLike = {
  nodeType: number;
  nodeName: string;
  textContent: string | null;
  childNodes: ArrayLike<NodeLike>;
  getAttribute?(name: string): string | null;
};

const TEXT = 3;
const ELEMENT = 1;
const BLOCKS = new Set(["DIV", "P"]);

/** Merge neighbouring text runs and drop empty ones. */
export function normalizeRuns(runs: Run[]): Run[] {
  const out: Run[] = [];

  for (const run of runs) {
    if ("text" in run) {
      if (!run.text) continue;
      const last = out.at(-1);

      if (last && "text" in last) out[out.length - 1] = { text: last.text + run.text };
      else out.push({ text: run.text });
    } else out.push(run);
  }

  return out;
}

/** DOM of the inline editor -> runs. `<br>` and block elements are line breaks; padding `<br data-pad>` is ignored. */
export function domToRuns(root: NodeLike): Run[] {
  const runs: Run[] = [];

  const walk = (node: NodeLike) => {
    if (node.nodeType === TEXT) {
      runs.push({ text: (node.textContent ?? "").replace(/​/g, "") });

      return;
    }
    if (node.nodeType !== ELEMENT) return;
    const attr = (n: string) => node.getAttribute?.(n) ?? null;

    if (node.nodeName === "BR") {
      if (attr("data-pad") === null) runs.push({ text: "\n" });

      return;
    }
    const field = attr("data-field");

    if (field) {
      const format = attr("data-format");

      runs.push(format ? { field, format } : { field });

      return;
    }
    const male = attr("data-male");

    if (male !== null) {
      runs.push({ gender: { male, female: attr("data-female") ?? "" } });

      return;
    }
    if (BLOCKS.has(node.nodeName) && runs.length) runs.push({ text: "\n" });
    Array.from(node.childNodes).forEach(walk);
  };

  Array.from(root.childNodes).forEach(walk);

  return normalizeRuns(runs);
}

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export const CHIP_CLASS = "cert-chip";

export function chipHtml(run: Run, label: (field: string) => string): string {
  if ("field" in run) {
    const fmt = run.format ? ` data-format="${escapeHtml(run.format)}"` : "";

    return `<span class="${CHIP_CLASS}" contenteditable="false" data-field="${escapeHtml(run.field)}"${fmt}>${escapeHtml(label(run.field))}</span>`;
  }
  if ("gender" in run) {
    const { male, female } = run.gender;

    return `<span class="${CHIP_CLASS} ${CHIP_CLASS}-gender" contenteditable="false" data-male="${escapeHtml(male)}" data-female="${escapeHtml(female)}">${escapeHtml(male)} / ${escapeHtml(female)}</span>`;
  }

  return "";
}

/** Runs -> HTML for the inline editor. A trailing line break gets a padding `<br data-pad>` so the empty line shows. */
export function runsToHtml(runs: Run[], label: (field: string) => string): string {
  let html = "";

  for (const run of runs) {
    if ("text" in run) html += escapeHtml(run.text).replace(/\n/g, "<br>");
    else html += chipHtml(run, label);
  }
  if (html.endsWith("<br>") || html === "") html += '<br data-pad="1">';

  return html;
}

/** What the layer shows: the runs with sample values (or a placeholder for an unknown field). */
export function resolveRuns(
  runs: Run[],
  values: Record<string, string>,
  gender: "male" | "female" | null,
  dateFields: ReadonlySet<string> = new Set(),
): string {
  return runs
    .map((run) => {
      if ("text" in run) return run.text;
      if ("field" in run) {
        const v = values[run.field] ?? "";

        return dateFields.has(run.field) ? formatDate(v, run.format) : v;
      }

      return gender === "female" ? run.gender.female : run.gender.male;
    })
    .join("");
}

export function runsPlain(runs: Run[], label: (field: string) => string): string {
  return runs
    .map((run) => ("text" in run ? run.text : "field" in run ? `[${label(run.field)}]` : `${run.gender.male}/${run.gender.female}`))
    .join("");
}

export function hasField(runs: Run[]): boolean {
  return runs.some((r) => "field" in r);
}
