// Certificate layout schema v1 (mirrors apps/api/app/certificates/layout.py) and the catalog the API serves.

export type Run =
  | { text: string }
  | { field: string; format?: string | null }
  | { gender: { male: string; female: string } };

export type TextStyle = {
  font: string;
  weight: number;
  italic: boolean;
  size_pt: number;
  min_size_pt: number | null;
  color: string;
  align: "left" | "center" | "right";
  valign: "top" | "middle" | "bottom";
  line_height: number;
  letter_spacing_pt: number;
  uppercase: boolean;
};

export type Box = {
  id: string;
  x_mm: number;
  y_mm: number;
  w_mm: number;
  h_mm: number;
  rotation: number;
  locked: boolean;
};

export type TextLayer = Box & { type: "text"; style: TextStyle; content: Run[] };
export type ImageSource = { asset: string } | { signature: "instructor" | "director" } | { company: "seal" };
export type ImageLayer = Box & { type: "image"; source: ImageSource; fit: "contain" };
export type QrLayer = Box & { type: "qr"; color: string };
export type LineLayer = Box & { type: "line"; color: string; thickness_mm: number; dash: boolean };
export type RectLayer = Box & { type: "rect"; fill: string };
export type Layer = TextLayer | ImageLayer | QrLayer | LineLayer | RectLayer;
export type LayerType = Layer["type"];

export type Layout = {
  schema: 1;
  page: { width_mm: number; height_mm: number };
  background: { asset: string } | null;
  layers: Layer[];
};

export type SampleKind = "short" | "long" | "female";

export type CertField = { key: string; label: string; group: string; type: "text" | "date" };
export type CertFont = { family: string; weights: number[]; italic_weights: number[] };
export type CertCatalog = {
  fields: CertField[];
  samples: Record<SampleKind, Record<string, string>>;
  fonts: CertFont[];
  date_formats: string[];
  date_format_examples: Record<string, string>;
};

export type TemplateStatus = "draft" | "published" | "archived" | string;

export type TemplateListItem = {
  id: string;
  key: string;
  name: string;
  status: TemplateStatus;
  lang: string;
  version: number;
  latest_version_no: number | null;
  updated_at: string;
  has_unpublished_changes: boolean;
};

export type TemplateRule = {
  course_id: string;
  course_name?: string;
  instructor_id: string | null;
  instructor_name?: string | null;
  template_id: string;
  template_name?: string;
};

export type TemplateDetail = {
  id: string;
  key: string;
  name: string;
  status: TemplateStatus;
  lang: string;
  version: number;
  draft: Layout;
  updated_at: string;
  latest_version_no: number | null;
  has_unpublished_changes: boolean;
  versions: { version_no: number; published_at: string; published_by_name: string | null }[];
  rules: TemplateRule[];
};

export type CertSettings = {
  director_name: string;
  director_title: string;
  signature_asset_id: string | null;
  seal_asset_id: string | null;
  version: number;
  updated_at: string;
  updated_by: string | null;
};

export type CertAsset = { id: string; kind: string; mime: string; width_px: number; height_px: number; size_bytes: number };

export const PAGE_FORMATS = [
  { key: "a4l", label: "A4 альбомная", width_mm: 297, height_mm: 210 },
  { key: "a4p", label: "A4 книжная", width_mm: 210, height_mm: 297 },
  { key: "a5l", label: "A5 альбомная", width_mm: 210, height_mm: 148 },
] as const;
