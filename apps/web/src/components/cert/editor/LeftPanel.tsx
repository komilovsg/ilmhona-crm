"use client";

import { useMemo, useRef, useState, type Dispatch } from "react";
import clsx from "clsx";

import { Icon } from "@/components/Icon";
import { Segmented } from "@/components/Segmented";
import { BLOCKS, layerName, type BlockKey } from "@/lib/cert-editor/blocks";
import type { Action, EditorState } from "@/lib/cert-editor/reducer";
import type { CertCatalog } from "@/lib/cert-editor/types";
import { BLOCK_MIME } from "./Canvas";

type Tab = "blocks" | "fields" | "layers";

export function LeftPanel({
  state,
  dispatch,
  catalog,
  label,
  canEdit,
  busy,
  onAddBlock,
  onInsertField,
  onBackground,
}: {
  state: EditorState;
  dispatch: Dispatch<Action>;
  catalog: CertCatalog | undefined;
  label: (field: string) => string;
  canEdit: boolean;
  busy: boolean;
  onAddBlock: (key: BlockKey) => void;
  onInsertField: (key: string) => void;
  onBackground: (file: File | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("blocks");
  const [q, setQ] = useState("");
  const bg = useRef<HTMLInputElement>(null);
  const groups = useMemo(() => {
    const out = new Map<string, NonNullable<CertCatalog["fields"]>>();
    const needle = q.trim().toLowerCase();

    for (const f of catalog?.fields ?? []) {
      if (needle && !f.label.toLowerCase().includes(needle) && !f.key.toLowerCase().includes(needle)) continue;
      out.set(f.group, [...(out.get(f.group) ?? []), f]);
    }

    return [...out];
  }, [catalog, q]);
  const stop = (e: React.MouseEvent) => e.preventDefault();

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-divider bg-content1" data-testid="left-panel">
      <div className="border-b border-divider p-2" onMouseDown={(e) => e.preventDefault()}>
        <Segmented
          className="!h-10 w-full [&>button]:!h-8 [&>button]:flex-1 [&>button]:!px-2"
          label="Панель"
          options={[
            { key: "blocks", label: "Блоки" },
            { key: "fields", label: "Поля" },
            { key: "layers", label: `Слои` },
          ]}
          value={tab}
          onChange={setTab}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {tab === "blocks" && (
          <div className="space-y-3">
            <p className="text-xs text-default-500">Нажмите или перетащите блок на лист.</p>
            <div className="grid grid-cols-2 gap-2">
              {BLOCKS.map((b) => (
                <button
                  key={b.key}
                  className="flex min-h-16 flex-col items-center justify-center gap-1 rounded-xl border border-divider bg-content2 p-2 text-center text-xs transition-colors hover:border-primary disabled:opacity-40"
                  disabled={!canEdit || busy}
                  draggable={canEdit}
                  title={b.hint}
                  type="button"
                  onClick={() => onAddBlock(b.key)}
                  onDragStart={(e) => {
                    e.dataTransfer.setData(BLOCK_MIME, b.key);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                >
                  <Icon name={b.icon} size={18} />
                  {b.label}
                </button>
              ))}
            </div>
            <div className="rounded-xl border border-divider p-2">
              <p className="mb-2 text-xs font-medium">Фон</p>
              <p className="mb-2 text-xs text-default-500">{state.layout.background ? "Фоновое изображение задано." : "Фона нет: белый лист."}</p>
              <input ref={bg} accept="image/png,image/jpeg" className="hidden" data-testid="background-file" type="file" onChange={(e) => { onBackground(e.target.files?.[0] ?? null); e.target.value = ""; }} />
              <div className="flex flex-wrap gap-2">
                <button className="rounded-lg bg-content2 px-3 py-1.5 text-xs hover:bg-content3 disabled:opacity-40" disabled={!canEdit || busy} type="button" onClick={() => bg.current?.click()}>
                  {state.layout.background ? "Заменить" : "Загрузить"}
                </button>
                {state.layout.background && (
                  <button className="rounded-lg px-3 py-1.5 text-xs text-danger hover:bg-danger/10 disabled:opacity-40" disabled={!canEdit} type="button" onClick={() => onBackground(null)}>
                    Убрать
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
        {tab === "fields" && (
          <div className="space-y-3">
            <input
              aria-label="Поиск поля"
              className="h-9 w-full rounded-lg border border-divider bg-content2 px-3 text-sm outline-none focus:border-primary"
              placeholder="Найти поле"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <p className="text-xs text-default-500">Нажмите поле: оно встанет в выбранный текст (или создаст новый).</p>
            {groups.length === 0 && <p className="text-sm text-default-500">Ничего не найдено.</p>}
            {groups.map(([group, fields]) => (
              <section key={group}>
                <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-default-500">{group}</h3>
                <ul className="space-y-1">
                  {fields.map((f) => (
                    <li key={f.key}>
                      <button
                        className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-content2 disabled:opacity-40"
                        disabled={!canEdit}
                        type="button"
                        onClick={() => onInsertField(f.key)}
                        onMouseDown={stop}
                      >
                        <span className="cert-chip !m-0">{f.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
        {tab === "layers" && (
          <ul className="space-y-1" data-testid="layers-list">
            {state.layout.layers.length === 0 && <li className="text-sm text-default-500">Лист пуст.</li>}
            {[...state.layout.layers].reverse().map((l) => (
              <li key={l.id}>
                <button
                  className={clsx("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm", state.selection.includes(l.id) ? "bg-primary/15 text-brand-text" : "hover:bg-content2")}
                  type="button"
                  onClick={(e) => (e.shiftKey ? dispatch({ type: "toggle_select", id: l.id }) : dispatch({ type: "select", ids: [l.id] }))}
                >
                  <span className="min-w-0 flex-1 truncate">{layerName(l, label)}</span>
                  {l.locked && <Icon name="lock" size={14} />}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
