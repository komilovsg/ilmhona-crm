"use client";

import type { Dispatch } from "react";

import { Icon } from "@/components/Icon";
import { SIZE_PRESETS } from "@/lib/cert-editor/blocks";
import { PX_PER_MM } from "@/lib/cert-editor/geometry";
import type { Action, EditorState } from "@/lib/cert-editor/reducer";
import type { TextLayer } from "@/lib/cert-editor/types";
import { ToggleButton } from "../ui";
import { styleFn } from "./RightPanel";

export function Toolbar({
  state,
  dispatch,
  canEdit,
  scale,
  fit,
  onZoom,
  onFit,
}: {
  state: EditorState;
  dispatch: Dispatch<Action>;
  canEdit: boolean;
  scale: number;
  fit: boolean;
  onZoom: (pct: number) => void;
  onFit: () => void;
}) {
  const texts = state.layout.layers.filter((l): l is TextLayer => l.type === "text" && state.selection.includes(l.id));
  const first = texts[0];
  const off = !canEdit || !first;
  const patch = (p: Parameters<typeof styleFn>[0]) => dispatch({ type: "update", ids: texts.map((t) => t.id), fn: styleFn(p) });
  const pct = Math.round((scale / PX_PER_MM) * 100);

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-divider bg-content1 px-3 py-1.5" data-testid="toolbar">
      <ToggleButton disabled={!canEdit || state.past.length === 0} label="Отменить (Ctrl+Z)" onPress={() => dispatch({ type: "undo" })}>
        <Icon name="undo" size={16} />
      </ToggleButton>
      <ToggleButton disabled={!canEdit || state.future.length === 0} label="Повторить (Ctrl+Shift+Z)" onPress={() => dispatch({ type: "redo" })}>
        <Icon name="redo" size={16} />
      </ToggleButton>
      <span className="mx-1 h-5 w-px bg-divider" />
      <select
        aria-label="Размер текста"
        className="h-8 rounded-lg border border-divider bg-content2 px-2 text-sm disabled:opacity-40"
        disabled={off}
        value={SIZE_PRESETS.find((p) => p.pt === first?.style.size_pt)?.key ?? ""}
        onChange={(e) => {
          const p = SIZE_PRESETS.find((x) => x.key === e.target.value);

          if (p) patch({ size_pt: p.pt });
        }}
      >
        <option value="">{first ? `${first.style.size_pt} pt` : "Размер"}</option>
        {SIZE_PRESETS.map((p) => (
          <option key={p.key} value={p.key}>
            {p.label} · {p.pt} pt
          </option>
        ))}
      </select>
      <ToggleButton active={!!first && first.style.weight >= 600} disabled={off} label="Жирный" onPress={() => patch({ weight: first && first.style.weight >= 600 ? 400 : 700 })}>
        <Icon name="bold" size={16} />
      </ToggleButton>
      <ToggleButton active={first?.style.italic} disabled={off} label="Курсив" onPress={() => patch({ italic: !first?.style.italic })}>
        <Icon name="italic" size={16} />
      </ToggleButton>
      {(["left", "center", "right"] as const).map((a) => (
        <ToggleButton key={a} active={first?.style.align === a} disabled={off} label={`Выравнивание: ${a === "left" ? "слева" : a === "center" ? "по центру" : "справа"}`} onPress={() => patch({ align: a })}>
          <Icon name={`align-${a}`} size={16} />
        </ToggleButton>
      ))}
      <span className="ml-auto flex items-center gap-1">
        <ToggleButton label="Уменьшить" onPress={() => onZoom(Math.max(50, pct - 10))}>
          <Icon name="minus" size={16} />
        </ToggleButton>
        <span className="w-12 text-center text-sm tabular-nums" data-testid="zoom">
          {pct}%
        </span>
        <ToggleButton label="Увеличить" onPress={() => onZoom(Math.min(200, pct + 10))}>
          <Icon name="plus" size={16} />
        </ToggleButton>
        <ToggleButton active={fit} label="По ширине" onPress={onFit}>
          <span className="text-xs">По ширине</span>
        </ToggleButton>
      </span>
    </div>
  );
}
