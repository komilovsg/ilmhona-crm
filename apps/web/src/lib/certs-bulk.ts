// Pure logic of the bulk issue from Excel (no React, unit-tested with node --test).

export type BulkStatus = "ok" | "error" | "duplicate";

export type BulkItem = {
  row: number;
  name: string;
  course: string | null;
  issued_date: string | null;
  phone: string | null;
  status: BulkStatus;
  reason: string | null;
  note: string | null;
  linked: boolean;
};

export type BulkPreview = {
  template_name: string;
  branch_name: string;
  counts: Record<BulkStatus, number>;
  linked: number;
  items: BulkItem[];
};

export type BulkResult = {
  batch_id: string;
  count: number;
  items: { id: string; row: number; number: string; student_name: string; linked: boolean }[];
  skipped: BulkItem[];
};

export const BULK_MAX_ROWS = 500;
export const BULK_MAX_BYTES = 2 * 1024 * 1024;

export const STATUS_TEXT: Record<BulkStatus, string> = { ok: "Готов", error: "Ошибка", duplicate: "Повтор" };
export const STATUS_COLOR: Record<BulkStatus, "success" | "danger" | "warning"> = { ok: "success", error: "danger", duplicate: "warning" };

const FILE_REASONS: Record<string, string> = {
  not_xlsx: "Файл не похож на Excel (.xlsx). Скачайте шаблон и заполните его.",
  empty: "В файле нет строк со списком.",
  no_name_column: "Не найден столбец «ФИО». Используйте шаблон.",
  too_large: "Файл больше 2 МБ.",
  too_many_rows: `В списке больше ${BULK_MAX_ROWS} строк. Разделите его на несколько файлов.`,
};

/** The Russian reason of a 422 «cert_bulk_file»; null for any other error. */
export function bulkFileReason(error: unknown): string | null {
  if (typeof error !== "object" || error === null || (error as { code?: string }).code !== "cert_bulk_file") return null;
  const reason = (error as { params?: { reason?: string } }).params?.reason;

  return (reason && FILE_REASONS[reason]) || "Файл не подходит: нужен список .xlsx по шаблону.";
}

/** Check the file before it is sent: only .xlsx, at most 2 МБ. Returns the problem or null. */
export function fileProblem(file: { name: string; size: number }): string | null {
  if (!file.name.toLowerCase().endsWith(".xlsx")) return FILE_REASONS.not_xlsx;
  if (file.size > BULK_MAX_BYTES) return FILE_REASONS.too_large;

  return null;
}

/** «Выдать 12 сертификатов» */
export function issueLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word = mod10 === 1 && mod100 !== 11 ? "сертификат" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "сертификата" : "сертификатов";

  return `Выдать ${n} ${word}`;
}
