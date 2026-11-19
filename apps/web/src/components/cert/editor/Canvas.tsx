"use client";

import { useRef, useState, type CSSProperties, type Dispatch, type RefObject } from "react";
import clsx from "clsx";

import type { BlockKey } from "@/lib/cert-editor/blocks";
import { isOutside, rectOf, resizeRect, round1, SAFE_MARGIN_MM, snapMove, snapResize, type Guide, type Handle, type Rect } from "@/lib/cert-editor/geometry";
import { withRect, type Action, type EditorState } from "@/lib/cert-editor/reducer";
import type { Run } from "@/lib/cert-editor/types";
import { LayerView } from "./LayerView";
import type { EditorApi, View } from "./view";

export const BLOCK_MIME = "application/x-cert-block";
const HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const HANDLE_POS: Record<Handle, [string, string, string]> = {
  nw: ["0%", "0%", "nwse-resize"],
  n: ["50%", "0%", "ns-resize"],
  ne: ["100%", "0%", "nesw-resize"],
  e: ["100%", "50%", "ew-resize"],
  se: ["100%", "100%", "nwse-resize"],
  s: ["50%", "100%", "ns-resize"],
  sw: ["0%", "100%", "nesw-resize"],
  w: ["0%", "50%", "ew-resize"],
};

type Gesture =
  | { kind: "move"; x: number; y: number; primary: string; orig: Map<string, Rect>; started: boolean }
  | { kind: "resize"; x: number; y: number; id: string; handle: Handle; orig: Rect; started: boolean };

const mm = (n: number) => `calc(${n} * var(--mm))`;

export function Canvas({
  state,
  dispatch,
  view,
  editingId,
  setEditingId,
  editorApi,
  onDropBlock,
  onCommit,
}: {
  state: EditorState;
  dispatch: Dispatch<Action>;
  view: View;
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  editorApi: RefObject<EditorApi | null>;
  onDropBlock: (key: BlockKey, spot: { x: number; y: number }) => void;
  onCommit: (id: string, runs: Run[]) => void;
}) {
  const { layout, selection } = state;
  const { page } = layout;
  const sheet = useRef<HTMLDivElement>(null);
  const gesture = useRef<Gesture | null>(null);
  // pointer capture retargets the click to the sheet, so the layer under the press is remembered
  const pressed = useRef<string | null>(null);
  const [guides, setGuides] = useState<Guide[]>([]);
  const single = selection.length === 1 ? layout.layers.find((l) => l.id === selection[0]) : undefined;

  function down(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;

    if (editingId && target.closest(`[data-layer-id="${editingId}"]`)) return;
    const handle = target.closest<HTMLElement>("[data-handle]")?.dataset.handle as Handle | undefined;

    if (handle && single) {
      sheet.current?.setPointerCapture(e.pointerId);
      gesture.current = { kind: "resize", x: e.clientX, y: e.clientY, id: single.id, handle, orig: rectOf(single), started: false };

      return;
    }
    const id = target.closest<HTMLElement>("[data-layer-id]")?.dataset.layerId;

    pressed.current = id ?? null;
    if (!id) {
      dispatch({ type: "select", ids: [] });

      return;
    }
    let chosen = selection;

    if (e.shiftKey) {
      dispatch({ type: "toggle_select", id });
      chosen = selection.includes(id) ? selection.filter((s) => s !== id) : [...selection, id];
    } else if (!selection.includes(id)) {
      dispatch({ type: "select", ids: [id] });
      chosen = [id];
    }
    const movable = layout.layers.filter((l) => chosen.includes(l.id) && !l.locked);

    if (!chosen.includes(id) || !movable.some((l) => l.id === id)) return;
    sheet.current?.setPointerCapture(e.pointerId);
    gesture.current = { kind: "move", x: e.clientX, y: e.clientY, primary: id, orig: new Map(movable.map((l) => [l.id, rectOf(l)])), started: false };
  }

  function move(e: React.PointerEvent<HTMLDivElement>) {
    const g = gesture.current;

    if (!g) return;
    const dx = (e.clientX - g.x) / view.scale;
    const dy = (e.clientY - g.y) / view.scale;

    if (!g.started) {
      if (Math.hypot(e.clientX - g.x, e.clientY - g.y) < 3) return;
      g.started = true;
      dispatch({ type: "begin" });
    }
    const snapOn = !e.altKey;

    if (g.kind === "move") {
      const first = g.orig.get(g.primary);

      if (!first) return;
      const others = layout.layers.filter((l) => !g.orig.has(l.id)).map(rectOf);
      const snapped = snapMove({ ...first, x: first.x + dx, y: first.y + dy }, others, page, { enabled: snapOn, threshold: 6 / view.scale });
      const sx = snapped.rect.x - first.x;
      const sy = snapped.rect.y - first.y;

      setGuides(snapped.guides);
      dispatch({
        type: "update",
        ids: [...g.orig.keys()],
        live: true,
        fn: (l) => {
          const o = g.orig.get(l.id);

          return o ? withRect({ x: round1(o.x + sx), y: round1(o.y + sy), w: o.w, h: o.h })(l) : l;
        },
      });
    } else {
      const others = layout.layers.filter((l) => l.id !== g.id).map(rectOf);
      const raw = resizeRect(g.orig, g.handle, dx, dy);
      const snapped = snapResize(raw, g.handle, others, page, { enabled: snapOn, threshold: 6 / view.scale });
      const r = snapOn ? snapped.rect : { x: round1(raw.x), y: round1(raw.y), w: round1(raw.w), h: round1(raw.h) };

      setGuides(snapOn ? snapped.guides : []);
      dispatch({ type: "update", ids: [g.id], live: true, fn: withRect({ x: round1(r.x), y: round1(r.y), w: round1(r.w), h: round1(r.h) }) });
    }
  }

  function up() {
    const g = gesture.current;

    gesture.current = null;
    setGuides([]);
    if (g?.started) dispatch({ type: "end" });
  }

  const sheetStyle = {
    "--mm": `${view.scale}px`,
    width: mm(page.width_mm),
    height: mm(page.height_mm),
  } as CSSProperties;

  return (
    <div
      ref={sheet}
      className="cert-sheet relative bg-white shadow-lg"
      data-testid="cert-sheet"
      style={sheetStyle}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(BLOCK_MIME)) e.preventDefault();
      }}
      onDrop={(e) => {
        const key = e.dataTransfer.getData(BLOCK_MIME) as BlockKey;

        if (!key || !sheet.current) return;
        e.preventDefault();
        const r = sheet.current.getBoundingClientRect();

        onDropBlock(key, { x: (e.clientX - r.left) / view.scale, y: (e.clientY - r.top) / view.scale });
      }}
      onDoubleClick={() => {
        const layer = layout.layers.find((l) => l.id === pressed.current);

        if (layer?.type === "text" && !layer.locked) {
          dispatch({ type: "select", ids: [layer.id] });
          setEditingId(layer.id);
        }
      }}
      onPointerCancel={up}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
    >
      {layout.background && (
        // eslint-disable-next-line @next/next/no-img-element
        <img alt="" className="pointer-events-none absolute inset-0 h-full w-full select-none object-fill" draggable={false} src={`/api/v1/cert-assets/${layout.background.asset}`} />
      )}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute border border-dashed border-sky-400/60"
        style={{ left: mm(SAFE_MARGIN_MM), top: mm(SAFE_MARGIN_MM), right: mm(SAFE_MARGIN_MM), bottom: mm(SAFE_MARGIN_MM) }}
      />
      {layout.layers.map((l) => {
        const outside = isOutside(rectOf(l), page);
        const editing = editingId === l.id;

        return (
          <div
            key={l.id}
            className={clsx("absolute", outside && "outline-dashed outline-1 outline-red-500", !l.locked && selection.includes(l.id) && !editing && "cursor-move")}
            data-layer-id={l.id}
            data-outside={outside}
            style={{ left: mm(l.x_mm), top: mm(l.y_mm), width: mm(l.w_mm), height: mm(l.h_mm), transform: l.rotation ? `rotate(${l.rotation}deg)` : undefined }}
          >
            <LayerView editing={editing} editorApi={editorApi} layer={l} view={view} onCommit={onCommit} onExit={() => setEditingId(null)} />
          </div>
        );
      })}
      {layout.layers
        .filter((l) => selection.includes(l.id))
        .map((l) => (
          <div
            key={`sel-${l.id}`}
            className={clsx("pointer-events-none absolute ring-2", l.locked ? "ring-default-400" : "ring-primary", editingId === l.id && "ring-1")}
            data-selected={l.id}
            style={{ left: mm(l.x_mm), top: mm(l.y_mm), width: mm(l.w_mm), height: mm(l.h_mm), transform: l.rotation ? `rotate(${l.rotation}deg)` : undefined }}
          >
            {single?.id === l.id && !l.locked && !editingId &&
              HANDLES.map((h) => (
                <span
                  key={h}
                  className="pointer-events-auto absolute size-2.5 rounded-sm border border-primary bg-white"
                  data-handle={h}
                  style={{ left: HANDLE_POS[h][0], top: HANDLE_POS[h][1], cursor: HANDLE_POS[h][2], transform: "translate(-50%,-50%)" }}
                />
              ))}
          </div>
        ))}
      {guides.map((g, i) => (
        <div
          key={i}
          className="pointer-events-none absolute bg-fuchsia-500"
          data-guide={g.axis}
          style={g.axis === "x" ? { left: mm(g.pos), top: 0, bottom: 0, width: 1 } : { top: mm(g.pos), left: 0, right: 0, height: 1 }}
        />
      ))}
    </div>
  );
}
