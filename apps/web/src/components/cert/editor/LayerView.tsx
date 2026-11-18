"use client";

import { memo, useCallback, useMemo, useEffect, useLayoutEffect, useRef, useSyncExternalStore } from "react";

import { fitSteps, pickFit } from "@/lib/cert-editor/fit";
import { PT_MM } from "@/lib/cert-editor/geometry";
import { CHIP_CLASS, chipHtml, domToRuns, hasField, resolveRuns, runsToHtml } from "@/lib/cert-editor/runs";
import type { ImageLayer, Layer, QrLayer, Run, TextLayer } from "@/lib/cert-editor/types";
import type { EditorApi, View } from "./view";

let fontsGen = 0;

function subscribeFonts(cb: () => void) {
  const on = () => {
    fontsGen++;
    cb();
  };

  document.fonts?.addEventListener("loadingdone", on);

  return () => document.fonts?.removeEventListener("loadingdone", on);
}

/** Bumps when a bundled font finishes loading, so the fit preview measures again. */
function useFontsTick(): number {
  return useSyncExternalStore(subscribeFonts, () => fontsGen, () => 0);
}

const mm = (n: number) => `calc(${n} * var(--mm))`;

function TextView({ layer, view, editing, apiRef, onCommit, onExit }: { layer: TextLayer; view: View; editing: boolean; apiRef: React.RefObject<EditorApi | null>; onCommit: (runs: Run[]) => void; onExit: () => void }) {
  const wrap = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const tick = useFontsTick();
  const s = layer.style;
  const values = view.catalog?.samples[view.sample];
  const gender = values?.gender === "female" ? "female" : "male";
  const dateFields = useMemo(() => new Set((view.catalog?.fields ?? []).filter((f) => f.type === "date").map((f) => f.key)), [view.catalog]);
  const sampleMode = view.showSample && !!values && !editing;

  // shrink-to-fit preview: smaller in 0.5 pt steps until the text fits, red outline when even the minimum does not
  useLayoutEffect(() => {
    const w = wrap.current;
    const el = inner.current;

    if (!w || !el) return;
    const fits = (pt: number) => {
      el.style.fontSize = `calc(${pt * PT_MM} * var(--mm))`;

      return el.offsetHeight <= w.clientHeight + 1 && el.scrollWidth <= w.clientWidth + 1;
    };
    // chips show field names, not values: the fit is only meaningful with sample data (or without fields)
    const measurable = sampleMode || !hasField(layer.content);
    const { pt, overflow } = measurable ? pickFit(fitSteps(s.size_pt, s.min_size_pt), fits) : { pt: s.size_pt, overflow: false };

    el.style.fontSize = `calc(${pt * PT_MM} * var(--mm))`;
    w.dataset.overflow = String(overflow);
    w.dataset.pt = String(pt);
  });
  void tick;

  const html = useRef("");

  useLayoutEffect(() => {
    const el = inner.current;

    if (!editing || !el) return;
    html.current = runsToHtml(layer.content, view.label);
    el.innerHTML = html.current;
    el.focus();
    const range = document.createRange();

    range.selectNodeContents(el);
    range.collapse(false);
    const sel = window.getSelection();

    sel?.removeAllRanges();
    sel?.addRange(range);
    // the editor is created once per editing session
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const commit = useCallback(() => {
    if (inner.current) onCommit(domToRuns(inner.current as unknown as Parameters<typeof domToRuns>[0]));
  }, [onCommit]);

  useEffect(() => {
    if (!editing) return;
    const el = inner.current;

    if (!el) return;
    const insertNode = (node: Node, after?: Node) => {
      el.focus();
      const sel = window.getSelection();
      const current = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
      const range = current && el.contains(current.startContainer) ? current : document.createRange();

      if (range !== current) {
        range.selectNodeContents(el);
        range.collapse(false);
      }
      range.deleteContents();
      range.insertNode(node);
      if (after) node.parentNode?.insertBefore(after, node.nextSibling);
      range.setStartAfter(after ?? node);
      range.collapse(true);
      sel?.removeAllRanges();
      sel?.addRange(range);
    };
    const chip = (run: Run) => {
      const t = document.createElement("template");

      t.innerHTML = chipHtml(run, view.label);
      const node = t.content.firstElementChild as HTMLElement;

      insertNode(node, document.createTextNode("​"));
      commit();
    };

    apiRef.current = {
      insertField: (key) => chip({ field: key }),
      insertGender: () => chip({ gender: { male: "прошёл", female: "прошла" } }),
      commit,
    };

    return () => {
      apiRef.current = null;
    };
  }, [editing, apiRef, commit, view]);

  const common: React.CSSProperties = {
    fontFamily: `"${s.font}", sans-serif`,
    fontWeight: s.weight,
    fontStyle: s.italic ? "italic" : "normal",
    color: s.color,
    textAlign: s.align,
    lineHeight: s.line_height,
    letterSpacing: s.letter_spacing_pt ? mm(s.letter_spacing_pt * PT_MM) : undefined,
    textTransform: s.uppercase ? "uppercase" : "none",
    whiteSpace: "pre-wrap",
    overflowWrap: "break-word",
    fontSize: mm(s.size_pt * PT_MM),
  };

  return (
    <div
      ref={wrap}
      className="cert-text flex h-full w-full flex-col"
      style={{ justifyContent: s.valign === "top" ? "flex-start" : s.valign === "middle" ? "center" : "flex-end" }}
    >
      {editing ? (
        <div
          ref={inner}
          contentEditable
          suppressContentEditableWarning
          aria-label="Текст блока"
          className="cert-editing outline-none"
          data-testid="inline-editor"
          style={common}
          onBlur={() => {
            commit();
            onExit();
          }}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") {
              commit();
              onExit();
            } else if (e.key === "Enter") {
              e.preventDefault();
              const sel = window.getSelection();

              if (!sel?.rangeCount) return;
              const range = sel.getRangeAt(0);

              range.deleteContents();
              const br = document.createElement("br");

              range.insertNode(br);
              if (!br.nextSibling) {
                const pad = document.createElement("br");

                pad.setAttribute("data-pad", "1");
                br.after(pad);
              }
              range.setStartAfter(br);
              range.collapse(true);
              sel.removeAllRanges();
              sel.addRange(range);
            }
          }}
          onPaste={(e) => {
            e.preventDefault();
            document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
          }}
        />
      ) : (
        <div ref={inner} style={common}>
          {sampleMode ? resolveRuns(layer.content, values, gender, dateFields) || " " : <RunsPreview runs={layer.content} label={view.label} />}
        </div>
      )}
    </div>
  );
}

function RunsPreview({ runs, label }: { runs: Run[]; label: (f: string) => string }) {
  if (!runs.length) return <span className="opacity-40">Пустой текст</span>;

  return (
    <>
      {runs.map((r, i) =>
        "text" in r ? (
          r.text
        ) : (
          <span
            key={i}
            className={`${CHIP_CLASS} ${"gender" in r ? `${CHIP_CLASS}-gender` : ""}`}
          >
            {"field" in r ? label(r.field) : `${r.gender.male} / ${r.gender.female}`}
          </span>
        ),
      )}
    </>
  );
}

function Placeholder({ text }: { text: string }) {
  return (
    <div className="flex h-full w-full items-center justify-center border border-dashed border-default-400 bg-default-100/60 p-1 text-center text-[11px] leading-tight text-default-500">
      {text}
    </div>
  );
}

function ImageView({ layer, view }: { layer: ImageLayer; view: View }) {
  const src = layer.source;
  let url: string | null = null;
  let hint = "Картинка";

  if ("asset" in src) {
    url = src.asset ? `/api/v1/cert-assets/${src.asset}` : null;
  } else if ("signature" in src) {
    hint = src.signature === "director" ? "Подпись директора" : "Подпись инструктора";
    if (src.signature === "director" && view.settings?.signature_asset_id) url = `/api/v1/cert-settings/signature?v=${view.settings.version}`;
    else if (src.signature === "instructor") hint = "Подпись инструктора (из карточки)";
  } else {
    hint = "Печать";
    if (view.settings?.seal_asset_id) url = `/api/v1/cert-settings/seal?v=${view.settings.version}`;
  }
  // eslint-disable-next-line @next/next/no-img-element
  if (url) return <img alt="" className="pointer-events-none h-full w-full select-none object-contain" draggable={false} src={url} />;

  return <Placeholder text={hint} />;
}

/** A deterministic QR-like graphic: finder squares and a fixed module pattern. */
function QrView({ layer }: { layer: QrLayer }) {
  const n = 21;
  const cells: React.ReactNode[] = [];
  const finder = (x: number, y: number) => (x < 7 && y < 7) || (x > 13 && y < 7) || (x < 7 && y > 13);

  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      let on: boolean;

      if (finder(x, y)) {
        const lx = x % 14 > 6 ? x - 14 : x;
        const ly = y > 13 ? y - 14 : y;
        const edge = lx === 0 || lx === 6 || ly === 0 || ly === 6;
        const core = lx >= 2 && lx <= 4 && ly >= 2 && ly <= 4;

        on = edge || core;
      } else on = ((x * 7 + y * 13 + x * y) % 5) < 2;
      if (on) cells.push(<rect key={`${x}-${y}`} height="1" width="1" x={x} y={y} />);
    }

  return (
    <svg className="h-full w-full" fill={layer.color} preserveAspectRatio="xMidYMid meet" viewBox={`0 0 ${n} ${n}`}>
      {cells}
    </svg>
  );
}

export const LayerView = memo(function LayerView({
  layer,
  view,
  editing,
  editorApi,
  onCommit,
  onExit,
}: {
  layer: Layer;
  view: View;
  editing: boolean;
  editorApi: React.RefObject<EditorApi | null>;
  onCommit: (id: string, runs: Run[]) => void;
  onExit: () => void;
}) {
  const body = (() => {
    switch (layer.type) {
      case "text":
        return <TextView apiRef={editorApi} editing={editing} layer={layer} view={view} onCommit={(r) => onCommit(layer.id, r)} onExit={onExit} />;
      case "image":
        return <ImageView layer={layer} view={view} />;
      case "qr":
        return <QrView layer={layer} />;
      case "line":
        return (
          <div
            className="absolute inset-x-0 top-1/2 -translate-y-1/2"
            style={{
              height: mm(layer.thickness_mm),
              background: layer.dash ? `repeating-linear-gradient(90deg, ${layer.color} 0 ${mm(layer.thickness_mm * 4)}, transparent 0 ${mm(layer.thickness_mm * 7)})` : layer.color,
            }}
          />
        );
      case "rect":
        return <div className="h-full w-full" style={{ background: layer.fill }} />;
    }
  })();

  return <>{body}</>;
});
