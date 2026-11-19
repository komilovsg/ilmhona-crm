"use client";

import { type Dispatch } from "react";

import { Button } from "@heroui/button";

import { Icon } from "@/components/Icon";
import { SIZE_PRESETS, TYPE_LABEL } from "@/lib/cert-editor/blocks";
import type { Action, EditorState, ZOrder } from "@/lib/cert-editor/reducer";
import { PAGE_FORMATS, type CertCatalog, type ImageLayer, type Layer, type TemplateDetail, type TextLayer, type TextStyle } from "@/lib/cert-editor/types";
import { LANGS } from "../TemplatesTab";
import { ColorField, NumField, Row, SelectNative, TextField, ToggleButton } from "../ui";
import type { EditorApi } from "./view";

const long = new Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Dushanbe", dateStyle: "medium", timeStyle: "short" });

/** Apply a style change to a text layer; the fit minimum follows the size when «Умещать в рамку» is off. */
export function styleFn(patch: Partial<TextStyle>) {
  return (l: Layer): Layer => {
    if (l.type !== "text") return l;
    const style = { ...l.style, ...patch };
    const wasFit = (l.style.min_size_pt ?? l.style.size_pt) < l.style.size_pt;

    if (patch.size_pt !== undefined) style.min_size_pt = wasFit ? Math.min(l.style.min_size_pt ?? patch.size_pt, patch.size_pt) : patch.size_pt;

    return { ...l, style };
  };
}

export function RightPanel({
  state,
  dispatch,
  catalog,
  label,
  canEdit,
  detail,
  name,
  lang,
  onName,
  onLang,
  editorApi,
  onReplaceImage,
  onRestore,
}: {
  state: EditorState;
  dispatch: Dispatch<Action>;
  catalog: CertCatalog | undefined;
  label: (f: string) => string;
  canEdit: boolean;
  detail: TemplateDetail;
  name: string;
  lang: string;
  onName: (v: string) => void;
  onLang: (v: string) => void;
  editorApi: React.RefObject<EditorApi | null>;
  onReplaceImage: (id: string) => void;
  onRestore: (versionNo: number) => void;
}) {
  const { layout, selection } = state;
  const layer = selection.length === 1 ? layout.layers.find((l) => l.id === selection[0]) : undefined;

  return (
    <aside className="w-72 shrink-0 overflow-y-auto border-l border-divider bg-content1 p-3" data-testid="right-panel">
      <h2 className="mb-3 text-sm font-semibold">Настройки</h2>
      {selection.length > 1 ? (
        <div className="space-y-3 text-sm">
          <p>Выбрано блоков: {selection.length}</p>
          <p className="text-xs text-default-500">Стрелки двигают все, Ctrl+D дублирует, Delete удаляет.</p>
          <Button color="danger" isDisabled={!canEdit} size="sm" variant="flat" onPress={() => dispatch({ type: "delete" })}>
            Удалить выбранные
          </Button>
        </div>
      ) : layer ? (
        <LayerSettings key={layer.id} canEdit={canEdit} catalog={catalog} dispatch={dispatch} editorApi={editorApi} label={label} layer={layer} onReplaceImage={onReplaceImage} />
      ) : (
        <div className="space-y-3">
          <TextField disabled={!canEdit} label="Название" value={name} onChange={onName} />
          <SelectNative disabled={!canEdit} label="Язык" options={LANGS} value={lang} onChange={onLang} />
          <SelectNative
            disabled={!canEdit}
            label="Формат листа"
            options={[...PAGE_FORMATS.map((f) => ({ key: f.key as string, label: f.label })), { key: "custom", label: "Другой" }]}
            value={PAGE_FORMATS.find((f) => f.width_mm === layout.page.width_mm && f.height_mm === layout.page.height_mm)?.key ?? "custom"}
            onChange={(k) => {
              const f = PAGE_FORMATS.find((x) => x.key === k);

              if (f) dispatch({ type: "set_page", width_mm: f.width_mm, height_mm: f.height_mm });
            }}
          />
          <p className="text-xs text-default-500">
            {layout.page.width_mm} × {layout.page.height_mm} мм
          </p>
          <section>
            <h3 className="mb-1 text-xs font-medium text-default-500">История версий</h3>
            {detail.versions.length === 0 && <p className="text-sm text-default-500">Опубликованных версий пока нет.</p>}
            <ul className="space-y-1">
              {detail.versions.map((v) => (
                <li key={v.version_no} className="rounded-lg bg-content2 p-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">Версия {v.version_no}</span>
                    {canEdit && (
                      <Button className="h-7 min-w-0 px-2 text-xs" size="sm" variant="light" onPress={() => onRestore(v.version_no)}>
                        Вернуть в черновик
                      </Button>
                    )}
                  </div>
                  <div className="text-xs text-default-500">
                    {long.format(new Date(v.published_at))}
                    {v.published_by_name ? ` · ${v.published_by_name}` : ""}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </aside>
  );
}

function LayerSettings({
  layer,
  dispatch,
  catalog,
  label,
  canEdit,
  editorApi,
  onReplaceImage,
}: {
  layer: Layer;
  dispatch: Dispatch<Action>;
  catalog: CertCatalog | undefined;
  label: (f: string) => string;
  canEdit: boolean;
  editorApi: React.RefObject<EditorApi | null>;
  onReplaceImage: (id: string) => void;
}) {
  const id = layer.id;
  const set = (patch: Partial<Layer>, key?: string) => dispatch({ type: "update", ids: [id], fn: (l) => ({ ...l, ...patch }) as Layer, key: key ? `${id}:${key}` : undefined });
  const order = (to: ZOrder) => dispatch({ type: "reorder", id, to });

  return (
    <div className="space-y-3">
      <p className="text-xs text-default-500">{TYPE_LABEL[layer.type]}</p>
      <div className="grid grid-cols-2 gap-2">
        <NumField disabled={!canEdit} label="X, мм" testId="prop-x" value={layer.x_mm} onChange={(n) => set({ x_mm: n }, "x")} />
        <NumField disabled={!canEdit} label="Y, мм" testId="prop-y" value={layer.y_mm} onChange={(n) => set({ y_mm: n }, "y")} />
        <NumField disabled={!canEdit} label="Ширина, мм" min={2} testId="prop-w" value={layer.w_mm} onChange={(n) => set({ w_mm: n }, "w")} />
        <NumField disabled={!canEdit} label="Высота, мм" min={2} testId="prop-h" value={layer.h_mm} onChange={(n) => set({ h_mm: n }, "h")} />
        <NumField disabled={!canEdit} label="Поворот, °" max={360} min={-360} step={1} value={layer.rotation} onChange={(n) => set({ rotation: n }, "rot")} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input checked={layer.locked} disabled={!canEdit} type="checkbox" onChange={(e) => set({ locked: e.target.checked })} />
        Закрепить (нельзя двигать)
      </label>
      <Row label="Порядок">
        <div className="flex gap-1">
          <ToggleButton disabled={!canEdit} label="На передний план" onPress={() => order("front")}>
            <Icon name="arrow-up" size={14} />
            <span className="ml-1 text-xs">Наверх</span>
          </ToggleButton>
          <ToggleButton disabled={!canEdit} label="Выше" onPress={() => order("up")}>
            <Icon name="chevron-right" size={14} className="-rotate-90" />
          </ToggleButton>
          <ToggleButton disabled={!canEdit} label="Ниже" onPress={() => order("down")}>
            <Icon name="chevron-right" size={14} className="rotate-90" />
          </ToggleButton>
          <ToggleButton disabled={!canEdit} label="На задний план" onPress={() => order("back")}>
            <Icon name="arrow-down" size={14} />
            <span className="ml-1 text-xs">Вниз</span>
          </ToggleButton>
        </div>
      </Row>
      <hr className="border-divider" />
      {layer.type === "text" && <TextSettings canEdit={canEdit} catalog={catalog} dispatch={dispatch} editorApi={editorApi} label={label} layer={layer} />}
      {layer.type === "image" && <ImageSettings canEdit={canEdit} layer={layer} onReplace={() => onReplaceImage(id)} onSource={(source) => set({ source })} />}
      {layer.type === "qr" && <ColorField disabled={!canEdit} label="Цвет" value={layer.color} onChange={(color) => set({ color }, "color")} />}
      {layer.type === "line" && (
        <div className="space-y-3">
          <ColorField disabled={!canEdit} label="Цвет" value={layer.color} onChange={(color) => set({ color }, "color")} />
          <NumField disabled={!canEdit} label="Толщина, мм" max={20} min={0.1} value={layer.thickness_mm} onChange={(n) => set({ thickness_mm: n }, "thick")} />
          <label className="flex items-center gap-2 text-sm">
            <input checked={layer.dash} disabled={!canEdit} type="checkbox" onChange={(e) => set({ dash: e.target.checked })} />
            Пунктир
          </label>
        </div>
      )}
      {layer.type === "rect" && <ColorField disabled={!canEdit} label="Заливка" value={layer.fill} onChange={(fill) => set({ fill }, "fill")} />}
      {canEdit && (
        <Button color="danger" size="sm" startContent={<Icon name="trash" size={16} />} variant="flat" onPress={() => dispatch({ type: "delete" })}>
          Удалить блок
        </Button>
      )}
    </div>
  );
}

function ImageSettings({ layer, canEdit, onSource, onReplace }: { layer: ImageLayer; canEdit: boolean; onSource: (s: ImageLayer["source"]) => void; onReplace: () => void }) {
  const kind = "asset" in layer.source ? "asset" : "signature" in layer.source ? `sig-${layer.source.signature}` : "seal";

  return (
    <div className="space-y-3">
      <SelectNative
        disabled={!canEdit}
        label="Источник"
        options={[
          { key: "asset", label: "Загруженная картинка" },
          { key: "sig-director", label: "Подпись директора" },
          { key: "sig-instructor", label: "Подпись инструктора" },
          { key: "seal", label: "Печать компании" },
        ]}
        value={kind}
        onChange={(k) => onSource(k === "asset" ? { asset: "asset" in layer.source ? layer.source.asset : "" } : k === "seal" ? { company: "seal" } : { signature: k === "sig-director" ? "director" : "instructor" })}
      />
      {kind === "asset" && (
        <Button isDisabled={!canEdit} size="sm" startContent={<Icon name="upload" size={16} />} variant="flat" onPress={onReplace}>
          Заменить изображение
        </Button>
      )}
    </div>
  );
}


function TextSettings({ layer, dispatch, catalog, label, canEdit, editorApi }: { layer: TextLayer; dispatch: Dispatch<Action>; catalog: CertCatalog | undefined; label: (f: string) => string; canEdit: boolean; editorApi: React.RefObject<EditorApi | null> }) {
  const s = layer.style;
  const id = layer.id;
  const fonts = catalog?.fonts ?? [];
  const font = fonts.find((f) => f.family === s.font);
  const style = (patch: Partial<TextStyle>, key?: string) => dispatch({ type: "update", ids: [id], fn: styleFn(patch), key: key ? `${id}:${key}` : undefined });
  const fit = (s.min_size_pt ?? s.size_pt) < s.size_pt;
  const formats = (catalog?.date_formats ?? []).map((f) => ({ key: f, label: catalog?.date_format_examples?.[f] ? `${f} (${catalog.date_format_examples[f]})` : f }));
  const dateKeys = new Set((catalog?.fields ?? []).filter((f) => f.type === "date").map((f) => f.key));
  const content = (fn: (runs: TextLayer["content"]) => TextLayer["content"], key?: string) =>
    dispatch({ type: "update", ids: [id], fn: (l) => (l.type === "text" ? { ...l, content: fn(l.content) } : l), key: key ? `${id}:${key}` : undefined });

  return (
    <div className="space-y-3">
      <SelectNative disabled={!canEdit} label="Шрифт" options={(fonts.length ? fonts.map((f) => f.family) : [s.font]).map((f) => ({ key: f, label: f }))} value={s.font} onChange={(v) => style({ font: v })} />
      <div className="grid grid-cols-2 gap-2">
        <SelectNative disabled={!canEdit} label="Насыщенность" options={(font?.weights ?? [400, 700]).map((w) => ({ key: w, label: String(w) }))} value={font?.weights.includes(s.weight) ? s.weight : (font?.weights[0] ?? s.weight)} onChange={(v) => style({ weight: v })} />
        <Row label="Начертание">
          <ToggleButton active={s.italic} disabled={!canEdit || (font ? font.italic_weights.length === 0 : false)} label="Курсив" onPress={() => style({ italic: !s.italic })}>
            <Icon name="italic" size={14} />
          </ToggleButton>
        </Row>
      </div>
      <Row label="Размер">
        <div className="flex flex-wrap gap-1">
          {SIZE_PRESETS.map((p) => (
            <ToggleButton key={p.key} active={s.size_pt === p.pt} disabled={!canEdit} label={`${p.label}, ${p.pt} pt`} onPress={() => style({ size_pt: p.pt })}>
              <span className="text-xs">{p.label}</span>
            </ToggleButton>
          ))}
        </div>
      </Row>
      <NumField disabled={!canEdit} label="Размер, pt" max={200} min={1} step={0.5} testId="prop-size" value={s.size_pt} onChange={(n) => style({ size_pt: n }, "size")} />
      <label className="flex items-center gap-2 text-sm">
        <input checked={fit} data-testid="prop-fit" disabled={!canEdit} type="checkbox" onChange={(e) => style({ min_size_pt: e.target.checked ? Math.max(1, Math.round(s.size_pt * 0.7)) : s.size_pt })} />
        Умещать в рамку
      </label>
      {fit && <NumField disabled={!canEdit} label="Минимальный размер, pt" max={s.size_pt} min={1} step={0.5} value={s.min_size_pt ?? s.size_pt} onChange={(n) => style({ min_size_pt: Math.min(n, s.size_pt) }, "min")} />}
      <ColorField disabled={!canEdit} label="Цвет" value={s.color} onChange={(color) => style({ color }, "color")} />
      <Row label="Выравнивание">
        <div className="flex gap-1">
          {(["left", "center", "right"] as const).map((a) => (
            <ToggleButton key={a} active={s.align === a} disabled={!canEdit} label={`По ${a === "left" ? "левому краю" : a === "center" ? "центру" : "правому краю"}`} onPress={() => style({ align: a })}>
              <Icon name={`align-${a}`} size={14} />
            </ToggleButton>
          ))}
        </div>
      </Row>
      <SelectNative disabled={!canEdit} label="По вертикали" options={[{ key: "top", label: "Сверху" }, { key: "middle", label: "По центру" }, { key: "bottom", label: "Снизу" }]} value={s.valign} onChange={(v) => style({ valign: v })} />
      <div className="grid grid-cols-2 gap-2">
        <NumField disabled={!canEdit} label="Межстрочный" max={4} min={0.5} step={0.05} value={s.line_height} onChange={(n) => style({ line_height: n }, "lh")} />
        <NumField disabled={!canEdit} label="Межбуквенный, pt" max={50} min={-5} step={0.1} value={s.letter_spacing_pt} onChange={(n) => style({ letter_spacing_pt: n }, "ls")} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input checked={s.uppercase} disabled={!canEdit} type="checkbox" onChange={(e) => style({ uppercase: e.target.checked })} />
        ЗАГЛАВНЫЕ
      </label>
      <hr className="border-divider" />
      <Button
        data-testid="add-gender"
        isDisabled={!canEdit}
        size="sm"
        variant="flat"
        onMouseDown={(e) => e.preventDefault()}
        onPress={() => (editorApi.current ? editorApi.current.insertGender() : content((r) => [...r, { gender: { male: "прошёл", female: "прошла" } }]))}
      >
        Вставить «по роду»
      </Button>
      {layer.content.map((r, i) =>
        "gender" in r ? (
          <div key={i} className="grid grid-cols-2 gap-2 rounded-lg bg-content2 p-2">
            <TextField disabled={!canEdit} label="Он" value={r.gender.male} onChange={(v) => content((runs) => runs.map((x, j) => (j === i && "gender" in x ? { gender: { ...x.gender, male: v } } : x)), `g${i}m`)} />
            <TextField disabled={!canEdit} label="Она" value={r.gender.female} onChange={(v) => content((runs) => runs.map((x, j) => (j === i && "gender" in x ? { gender: { ...x.gender, female: v } } : x)), `g${i}f`)} />
          </div>
        ) : "field" in r && dateKeys.has(r.field) && formats.length ? (
          <SelectNative key={i} disabled={!canEdit} label={`Формат даты: ${label(r.field)}`} options={formats.map((f) => ({ key: f.key, label: f.label }))} value={r.format ?? formats[0].key} onChange={(v) => content((runs) => runs.map((x, j) => (j === i && "field" in x ? { ...x, format: v } : x)))} />
        ) : null,
      )}
    </div>
  );
}
