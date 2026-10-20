// Time is shown in Asia/Dushanbe whatever the browser's zone is (SPEC «Модель данных»).
const TZ = "Asia/Dushanbe";
const dateTime = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, dateStyle: "short", timeStyle: "short" });
const date = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function formatDate(iso: string | null | undefined): string {
  return iso ? date.format(new Date(iso)) : "—";
}
