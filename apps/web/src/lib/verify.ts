/** The public certificate check (`/v/<code>`): what the API answers and how the page words it. */

/** Exactly the fields the API returns (apps/api/app/certificates/public.py). */
export type PublicCertificate = {
  number: string;
  holder: string;
  course: string;
  cohort_start: string | null;
  cohort_end: string | null;
  issued_on: string;
  status: "valid" | "replaced" | "revoked";
  revoked_on: string | null;
  issuer: string;
};

export type CheckResult =
  | { kind: "found"; cert: PublicCertificate }
  | { kind: "not_found" }
  | { kind: "limit" }
  | { kind: "error" };

const ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
const CODE = new RegExp(`^[${ALPHABET}]{12}$`);

/** The code as the API stores it: case, spaces and dashes do not matter. Null when it cannot be one. */
export function normalizeCode(raw: string): string | null {
  const code = raw.slice(0, 64).replace(/[\s-]/g, "").toUpperCase();
  return CODE.test(code) ? code : null;
}

/** XXXX-XXXX-XXXX, as printed under the QR. */
export function showCode(code: string): string {
  return code.match(/.{1,4}/g)?.join("-") ?? code;
}

const MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(" ");

/** 2026-11-27 -> «27 ноября 2026». */
export function formatDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export const STATUS_TEXT: Record<PublicCertificate["status"], { title: string; note: (c: PublicCertificate) => string }> = {
  valid: { title: "Действителен", note: () => "Сертификат выдан ilmhona и действует." },
  revoked: {
    title: "Отозван",
    note: (c) => (c.revoked_on ? `Сертификат отозван ${formatDay(c.revoked_on)} и больше не действует.` : "Сертификат отозван и больше не действует."),
  },
  replaced: { title: "Заменён", note: () => "Этот экземпляр заменён новым сертификатом и больше не действует." },
};

/** «2 марта — 18 ноября 2026», or one date, or null. */
export function studyPeriod(c: PublicCertificate): string | null {
  if (c.cohort_start && c.cohort_end) return `${formatDay(c.cohort_start)} — ${formatDay(c.cohort_end)}`;
  const one = c.cohort_start ?? c.cohort_end;
  return one ? formatDay(one) : null;
}
