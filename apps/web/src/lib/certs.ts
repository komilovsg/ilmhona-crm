// Pure logic of certificate issue and download (no React, unit-tested with node --test).

import { PDFDocument } from "pdf-lib";
import { zipSync } from "fflate";

import { can, type Permissions } from "./permissions.ts";

export type CertStatus = "valid" | "replaced" | "revoked";
export type CertLang = "ru" | "en" | "tg";

export const STATUS_LABEL: Record<CertStatus, string> = { valid: "Действителен", replaced: "Заменён", revoked: "Аннулирован" };
export const STATUS_TONE: Record<CertStatus, "success" | "default" | "danger"> = { valid: "success", replaced: "default", revoked: "danger" };

export type CheckItem = {
  enrollment_id: string;
  student_name: string;
  enrollment_status: string;
  number: string | null;
  certificate_id: string | null;
  reason: string | null;
  text: string | null;
  score: number | null;
  status: "ready" | "issued" | "fix";
};

export type CheckResult = {
  template_id: string;
  template_name: string;
  lang: CertLang;
  allow_non_graduate: boolean;
  items: CheckItem[];
  counts: { ready: number; issued: number; fix: number };
};

export type IssuedCert = { id: string; number: string; student_name: string; enrollment_id: string; status: CertStatus; issued_at: string };

export type CertRow = {
  id: string;
  number: string;
  status: CertStatus;
  enrollment_id: string;
  student_id: string;
  student_name: string;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  branch_name: string;
  instructor_name: string | null;
  template_name: string;
  lang: CertLang;
  comment: string | null;
  revoke_reason: string | null;
  issued_at: string;
  issued_by: string | null;
};

export type NotReadyItem = { enrollment_id: string; student_name: string; reason: string; text: string };

/** «12 из 18» */
export function progressLabel(done: number, total: number): string {
  return `${done} из ${total}`;
}

/** Rows the user may tick: ready ones only (issued and «нужно исправить» stay unticked and disabled). */
export function selectable(items: CheckItem[]): CheckItem[] {
  return items.filter((i) => i.status === "ready");
}

export function issueLabel(count: number): string {
  return count > 0 ? `Выдать ${count}` : "Выдать";
}

/** Issue to a student who is not a graduate: the setting is on and the user may change templates. */
export function canIssueToNonGraduate(permissions: Permissions | undefined, allowNonGraduate: boolean): boolean {
  return allowNonGraduate && can(permissions, "cert_templates", "change");
}

/** A free file name inside one archive: `a.pdf`, `a (2).pdf`, ... */
export function uniqueName(name: string, used: Set<string>): string {
  let out = name;
  let n = 1;
  const dot = name.lastIndexOf(".");
  const [stem, ext] = dot > 0 ? [name.slice(0, dot), name.slice(dot)] : [name, ""];

  while (used.has(out)) out = `${stem} (${++n})${ext}`;
  used.add(out);

  return out;
}

export type PdfFile = { name: string; data: Uint8Array };

/**
 * Fetch the PDFs one by one, in the given order, reporting `done` after each. One failure stops the
 * run: a half-built package must not look complete.
 */
export async function fetchAll(
  ids: string[],
  fetchOne: (id: string) => Promise<{ data: Uint8Array; name: string | null }>,
  onProgress: (done: number, total: number) => void,
): Promise<PdfFile[]> {
  const used = new Set<string>();
  const files: PdfFile[] = [];

  onProgress(0, ids.length);
  for (const id of ids) {
    const { data, name } = await fetchOne(id);

    files.push({ name: uniqueName(name ?? `${id}.pdf`, used), data });
    onProgress(files.length, ids.length);
  }

  return files;
}

/** All pages of all files, in the order of `files`. */
export async function mergePdfs(files: PdfFile[]): Promise<Uint8Array> {
  const out = await PDFDocument.create();

  for (const f of files) {
    const doc = await PDFDocument.load(f.data);

    for (const page of await out.copyPages(doc, doc.getPageIndices())) out.addPage(page);
  }

  return out.save();
}

/** A ZIP of the separate PDFs (already compressed inside, so stored as is). */
export function zipPdfs(files: PdfFile[]): Uint8Array {
  return zipSync(Object.fromEntries(files.map((f) => [f.name, [f.data, { level: 0 }]])));
}
