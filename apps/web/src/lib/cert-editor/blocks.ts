// Building blocks of the left panel and the layer defaults.

import type { ImageLayer, Layer, LayerType, Layout, LineLayer, QrLayer, RectLayer, Run, TextLayer, TextStyle } from "./types.ts";

export const SIZE_PRESETS = [
  { key: "small", label: "Мелкий", pt: 10 },
  { key: "normal", label: "Обычный", pt: 14 },
  { key: "large", label: "Крупный", pt: 24 },
  { key: "xl", label: "Очень крупный", pt: 36 },
] as const;

export const DEFAULT_STYLE: TextStyle = {
  font: "Montserrat",
  weight: 400,
  italic: false,
  size_pt: 14,
  min_size_pt: 14,
  color: "#1f2933",
  align: "left",
  valign: "top",
  line_height: 1.2,
  letter_spacing_pt: 0,
  uppercase: false,
};

export const BLANK_LAYOUT: Layout = {
  schema: 1,
  page: { width_mm: 297, height_mm: 210 },
  background: null,
  layers: [],
};

/** A unique layer id (`text-3`): lowercase slug, as the API demands. */
export function newId(type: string, existing: string[]): string {
  const taken = new Set(existing);
  let n = 1;

  while (taken.has(`${type}-${n}`)) n++;

  return `${type}-${n}`;
}

type Spot = { x: number; y: number };

const at = (spot: Spot, w: number, h: number) => ({
  x_mm: Math.round((spot.x - w / 2) * 10) / 10,
  y_mm: Math.round((spot.y - h / 2) * 10) / 10,
  w_mm: w,
  h_mm: h,
  rotation: 0,
  locked: false,
});

export type BlockKey =
  | "text"
  | "name"
  | "number_date"
  | "qr"
  | "sig_instructor"
  | "sig_director"
  | "seal"
  | "director"
  | "image"
  | "line"
  | "rect";

export const BLOCKS: { key: BlockKey; label: string; icon: string; hint: string }[] = [
  { key: "text", label: "Текст", icon: "edit", hint: "Свободный текст" },
  { key: "name", label: "ФИО выпускника", icon: "students", hint: "Фамилия и имя" },
  { key: "number_date", label: "Номер и дата", icon: "master", hint: "Номер сертификата и дата выдачи" },
  { key: "qr", label: "QR-код", icon: "sliders", hint: "Ссылка на проверку" },
  { key: "sig_instructor", label: "Подпись инструктора", icon: "edit", hint: "Из карточки инструктора" },
  { key: "sig_director", label: "Подпись директора", icon: "edit", hint: "Из настроек сертификатов" },
  { key: "seal", label: "Печать", icon: "roles", hint: "Из настроек сертификатов" },
  { key: "director", label: "Директор", icon: "users", hint: "Имя и должность" },
  { key: "image", label: "Добавить изображение", icon: "upload", hint: "Загрузить PNG или SVG: логотип, иконка донора" },
  { key: "line", label: "Линия", icon: "grip", hint: "Разделитель" },
  { key: "rect", label: "Прямоугольник", icon: "rooms", hint: "Закрывает лишнее на фоне" },
];

function textLayer(id: string, spot: Spot, w: number, h: number, content: Run[], style: Partial<TextStyle> = {}): TextLayer {
  return { id, type: "text", ...at(spot, w, h), style: { ...DEFAULT_STYLE, ...style }, content };
}

/** The layers a block adds (the director block adds two). `asset` is the uploaded image for «Картинка». */
export function makeBlock(key: BlockKey, ids: string[], spot: Spot, asset?: { id: string; w: number; h: number }): Layer[] {
  const used = [...ids];
  const id = (type: string) => {
    const v = newId(type, used);

    used.push(v);

    return v;
  };

  switch (key) {
    case "text":
      return [textLayer(id("text"), spot, 80, 12, [{ text: "Текст" }])];
    case "name":
      return [
        textLayer(id("name"), spot, 200, 20, [{ field: "student.last_name" }, { text: " " }, { field: "student.first_name" }], {
          size_pt: 36,
          min_size_pt: 20,
          weight: 700,
          align: "center",
          valign: "middle",
        }),
      ];
    case "number_date":
      return [
        textLayer(id("number"), spot, 90, 8, [{ text: "№ " }, { field: "certificate.number" }, { text: " от " }, { field: "certificate.issued_date" }], {
          size_pt: 10,
          min_size_pt: 8,
          color: "#66727d",
        }),
      ];
    case "qr": {
      const layer: QrLayer = { id: id("qr"), type: "qr", color: "#000000", ...at(spot, 24, 24) };

      return [layer];
    }
    case "sig_instructor":
    case "sig_director": {
      const layer: ImageLayer = {
        id: id("signature"),
        type: "image",
        source: { signature: key === "sig_director" ? "director" : "instructor" },
        fit: "contain",
        ...at(spot, 40, 16),
      };

      return [layer];
    }
    case "seal": {
      const layer: ImageLayer = { id: id("seal"), type: "image", source: { company: "seal" }, fit: "contain", ...at(spot, 32, 32) };

      return [layer];
    }
    case "director": {
      const nameId = id("dir-name");
      const titleId = id("dir-title");

      return [
        textLayer(nameId, { x: spot.x, y: spot.y - 4 }, 60, 6.2, [{ field: "company.director_name" }], { weight: 700, size_pt: 14, min_size_pt: 10 }),
        textLayer(titleId, { x: spot.x, y: spot.y + 3 }, 60, 6.2, [{ field: "company.director_title" }], { size_pt: 10, min_size_pt: 8, color: "#66727d" }),
      ];
    }
    case "image": {
      const ratio = asset && asset.w > 0 && asset.h > 0 ? asset.w / asset.h : 1;
      const w = ratio >= 1 ? 50 : Math.round(50 * ratio * 10) / 10 || 30;
      const h = ratio >= 1 ? Math.round((50 / ratio) * 10) / 10 : 50;
      const layer: ImageLayer = { id: id("image"), type: "image", source: { asset: asset?.id ?? "" }, fit: "contain", ...at(spot, w, h) };

      return [layer];
    }
    case "line": {
      const layer: LineLayer = { id: id("line"), type: "line", color: "#3c3c3b", thickness_mm: 0.3, dash: false, ...at(spot, 60, 1) };

      return [layer];
    }
    case "rect": {
      const layer: RectLayer = { id: id("rect"), type: "rect", fill: "#ffffff", ...at(spot, 60, 20) };

      return [layer];
    }
  }
}

export function layerName(layer: Layer, label: (field: string) => string): string {
  switch (layer.type) {
    case "text": {
      const text = layer.content
        .map((r) => ("text" in r ? r.text : "field" in r ? label(r.field) : `${r.gender.male}/${r.gender.female}`))
        .join("")
        .replace(/\s+/g, " ")
        .trim();

      return text ? `Текст: ${text.slice(0, 28)}` : "Текст (пусто)";
    }
    case "image":
      return "signature" in layer.source
        ? layer.source.signature === "director"
          ? "Подпись директора"
          : "Подпись инструктора"
        : "company" in layer.source
          ? "Печать"
          : "Картинка";
    case "qr":
      return "QR-код";
    case "line":
      return "Линия";
    case "rect":
      return "Прямоугольник";
  }
}

export const TYPE_LABEL: Record<LayerType, string> = {
  text: "Текст",
  image: "Картинка",
  qr: "QR-код",
  line: "Линия",
  rect: "Прямоугольник",
};

/** «Начать с образца»: a simple starter certificate on a white A4 landscape sheet. */
export function sampleLayout(): Layout {
  const layers: Layer[] = [];
  const add = (key: BlockKey, x: number, y: number, patch?: (l: Layer) => Layer) => {
    for (const l of makeBlock(key, layers.map((i) => i.id), { x, y })) layers.push(patch ? patch(l) : l);
  };

  add("text", 148.5, 40, (l) =>
    l.type === "text"
      ? { ...l, w_mm: 200, content: [{ text: "СЕРТИФИКАТ" }], style: { ...l.style, size_pt: 40, min_size_pt: 40, weight: 700, align: "center" } }
      : l,
  );
  add("name", 148.5, 95);
  add("number_date", 148.5, 150);
  add("qr", 40, 170);
  add("director", 230, 175);

  return { ...BLANK_LAYOUT, layers };
}
