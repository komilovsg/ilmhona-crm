import type { CertCatalog, CertSettings, SampleKind } from "@/lib/cert-editor/types";

export type View = {
  /** CSS px per mm */
  scale: number;
  catalog: CertCatalog | undefined;
  sample: SampleKind;
  /** language of the template: the director sample follows it */
  lang: string;
  showSample: boolean;
  label: (field: string) => string;
  settings: CertSettings | undefined;
};

export type EditorApi = {
  insertField: (key: string) => void;
  insertGender: () => void;
  commit: () => void;
};
