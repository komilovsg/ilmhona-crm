// The editor state: layout + selection + undo history. Pure, no React.

import { newId } from "./blocks.ts";
import type { Layer, Layout } from "./types.ts";

export const HISTORY_LIMIT = 100;
export const DUPLICATE_OFFSET_MM = 5;

export type EditorState = {
  layout: Layout;
  /** The layout as last loaded / saved: the «Несохранённые изменения» marker compares against it. */
  saved: Layout;
  selection: string[];
  past: Layout[];
  future: Layout[];
  /** Key of the last coalesced edit (typing in one field is one undo step). */
  lastKey: string | null;
};

export type ZOrder = "front" | "back" | "up" | "down";

export type Action =
  | { type: "load"; layout: Layout }
  | { type: "saved"; layout?: Layout }
  /** The server's canonical copy of what was just saved replaces the local one (no history step). */
  | { type: "adopt"; layout: Layout }
  | { type: "select"; ids: string[] }
  | { type: "toggle_select"; id: string }
  | { type: "update"; ids: string[]; fn: (layer: Layer) => Layer; key?: string; live?: boolean }
  | { type: "begin" }
  | { type: "end" }
  | { type: "add"; layers: Layer[] }
  | { type: "nudge"; dx: number; dy: number }
  | { type: "duplicate" }
  | { type: "delete" }
  | { type: "reorder"; id: string; to: ZOrder }
  | { type: "set_layout"; layout: Layout }
  | { type: "set_page"; width_mm: number; height_mm: number }
  | { type: "set_background"; asset: string | null }
  | { type: "undo" }
  | { type: "redo" };

export function initialState(layout: Layout): EditorState {
  return { layout, saved: layout, selection: [], past: [], future: [], lastKey: null };
}

export function isDirty(s: EditorState): boolean {
  return s.layout !== s.saved && JSON.stringify(s.layout) !== JSON.stringify(s.saved);
}

function push(past: Layout[], layout: Layout): Layout[] {
  const next = [...past, layout];

  return next.length > HISTORY_LIMIT ? next.slice(next.length - HISTORY_LIMIT) : next;
}

/** Apply a layout change as one undo step. */
function record(s: EditorState, layout: Layout, selection = s.selection, key: string | null = null): EditorState {
  const ids = new Set(layout.layers.map((l) => l.id));
  const coalesce = key !== null && key === s.lastKey;

  return {
    ...s,
    layout,
    selection: selection.filter((id) => ids.has(id)),
    past: coalesce ? s.past : push(s.past, s.layout),
    future: [],
    lastKey: key,
  };
}

function withLayers(layout: Layout, layers: Layer[]): Layout {
  return { ...layout, layers };
}

export function reorder(layers: Layer[], id: string, to: ZOrder): Layer[] {
  const i = layers.findIndex((l) => l.id === id);

  if (i < 0) return layers;
  const next = [...layers];
  const [item] = next.splice(i, 1);
  const j = to === "front" ? next.length : to === "back" ? 0 : to === "up" ? Math.min(i + 1, next.length) : Math.max(i - 1, 0);

  next.splice(j, 0, item);

  return next;
}

export function reducer(s: EditorState, a: Action): EditorState {
  switch (a.type) {
    case "load":
      return initialState(a.layout);
    case "saved":
      return { ...s, saved: a.layout ?? s.layout };
    case "adopt":
      return { ...s, layout: a.layout, saved: a.layout };
    case "select":
      return { ...s, selection: a.ids.filter((id) => s.layout.layers.some((l) => l.id === id)), lastKey: null };
    case "toggle_select":
      return {
        ...s,
        selection: s.selection.includes(a.id) ? s.selection.filter((id) => id !== a.id) : [...s.selection, a.id],
        lastKey: null,
      };
    case "begin":
      return { ...s, past: push(s.past, s.layout), future: [], lastKey: null };
    case "end": {
      const top = s.past.at(-1);

      return top && JSON.stringify(top) === JSON.stringify(s.layout) ? { ...s, past: s.past.slice(0, -1) } : s;
    }
    case "update": {
      const ids = new Set(a.ids);
      const layers = s.layout.layers.map((l) => (ids.has(l.id) ? a.fn(l) : l));
      const layout = withLayers(s.layout, layers);

      return a.live ? { ...s, layout } : record(s, layout, s.selection, a.key ?? null);
    }
    case "add": {
      const layout = withLayers(s.layout, [...s.layout.layers, ...a.layers]);

      return record(s, layout, a.layers.map((l) => l.id));
    }
    case "nudge": {
      const layers = s.layout.layers.map((l) =>
        s.selection.includes(l.id) && !l.locked ? { ...l, x_mm: l.x_mm + a.dx, y_mm: l.y_mm + a.dy } : l,
      );

      return layers.some((l, i) => l !== s.layout.layers[i]) ? record(s, withLayers(s.layout, layers), s.selection, "nudge") : s;
    }
    case "duplicate": {
      const chosen = s.layout.layers.filter((l) => s.selection.includes(l.id));

      if (!chosen.length) return s;
      const ids = s.layout.layers.map((l) => l.id);
      const copies = chosen.map((l) => {
        const id = newId(l.id.replace(/-\d+$/, "") || l.type, ids);

        ids.push(id);

        return { ...structuredClone(l), id, x_mm: l.x_mm + DUPLICATE_OFFSET_MM, y_mm: l.y_mm + DUPLICATE_OFFSET_MM, locked: false };
      });

      return record(s, withLayers(s.layout, [...s.layout.layers, ...copies]), copies.map((c) => c.id));
    }
    case "delete": {
      if (!s.selection.length) return s;

      return record(s, withLayers(s.layout, s.layout.layers.filter((l) => !s.selection.includes(l.id))), []);
    }
    case "reorder": {
      const layers = reorder(s.layout.layers, a.id, a.to);

      return layers === s.layout.layers ? s : record(s, withLayers(s.layout, layers));
    }
    case "set_layout":
      return record(s, a.layout, []);
    case "set_page":
      return record(s, { ...s.layout, page: { width_mm: a.width_mm, height_mm: a.height_mm } }, s.selection, "page");
    case "set_background":
      return record(s, { ...s.layout, background: a.asset ? { asset: a.asset } : null });
    case "undo": {
      const prev = s.past.at(-1);

      if (!prev) return s;
      const ids = new Set(prev.layers.map((l) => l.id));

      return {
        ...s,
        layout: prev,
        past: s.past.slice(0, -1),
        future: [s.layout, ...s.future].slice(0, HISTORY_LIMIT),
        selection: s.selection.filter((id) => ids.has(id)),
        lastKey: null,
      };
    }
    case "redo": {
      const next = s.future[0];

      if (!next) return s;
      const ids = new Set(next.layers.map((l) => l.id));

      return {
        ...s,
        layout: next,
        past: push(s.past, s.layout),
        future: s.future.slice(1),
        selection: s.selection.filter((id) => ids.has(id)),
        lastKey: null,
      };
    }
  }
}

/** Geometry patch for a layer (move / resize). */
export const withRect = (r: { x: number; y: number; w: number; h: number }) => (l: Layer): Layer => ({
  ...l,
  x_mm: r.x,
  y_mm: r.y,
  w_mm: r.w,
  h_mm: r.h,
});
