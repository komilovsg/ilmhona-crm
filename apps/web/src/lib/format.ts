// Time is shown in Asia/Dushanbe whatever the browser's zone is (SPEC «Модель данных»).
const TZ = "Asia/Dushanbe";
const dateTime = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, dateStyle: "short", timeStyle: "short" });
const date = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

const day = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

/** `YYYY-MM-DD` of a timestamp in Asia/Dushanbe (never `iso.slice(0, 10)`: that is the UTC day). */
export function dushanbeDay(iso: string): string {
  return day.format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  return iso ? date.format(new Date(iso)) : "—";
}

/**
 * `tel:` target of a phone as typed by a person («+992 900 12-34-56», «900123456», «992900123456»):
 * digits only, with +992 for a local 9-digit number. Never contains spaces.
 */
export function telHref(phone: string): string {
  const digits = phone.replace(/\D/g, "");

  if (phone.trim().startsWith("+") || digits.length > 9) return `tel:+${digits}`;

  return digits.length === 9 ? `tel:+992${digits}` : `tel:${digits}`;
}
