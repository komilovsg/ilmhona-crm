// Pure helpers of the sales screens (unit-tested with node --test).

import { formatPrice } from "./education.ts";

export const LEAD_STATUSES = ["новый", "заинтересован", "нулевой урок", "записан", "отказ"] as const;
export const CALL_STATUSES = ["не звонили", "не ответил", "позвонили", "перезвонить"] as const;
export const LEAD_SOURCES = ["Facebook", "Instagram", "TikTok", "Telegram", "сайт", "рекомендация", "звонок", "другое"] as const;
export const PLATFORMS = ["Facebook Ads", "Instagram", "TikTok", "Telegram", "Google", "офлайн", "другое"] as const;
export const CAMPAIGN_STATUSES = ["запланирована", "активна", "остановлена", "завершена"] as const;

export type Tone = "default" | "primary" | "secondary" | "success" | "warning" | "danger";

export function leadTone(status: string): Tone {
  switch (status) {
    case "новый":
      return "primary";
    case "заинтересован":
      return "secondary";
    case "нулевой урок":
      return "warning";
    case "записан":
      return "success";
    case "отказ":
      return "danger";
    default:
      return "default";
  }
}

export function callTone(status: string): Tone {
  switch (status) {
    case "позвонили":
      return "success";
    case "не ответил":
      return "danger";
    case "перезвонить":
      return "warning";
    default:
      return "default";
  }
}

export function campaignTone(status: string): Tone {
  switch (status) {
    case "активна":
      return "success";
    case "остановлена":
      return "warning";
    case "запланирована":
      return "primary";
    default:
      return "default";
  }
}

/** Digits of a phone as the messengers want them: 992XXXXXXXXX (a local 9-digit number gets 992). */
export function messengerDigits(phone: string): string {
  const digits = phone.replace(/\D/g, "");

  return digits.length === 9 ? `992${digits}` : digits;
}

/** `https://wa.me/992…` — null when the text holds no usable number. */
export function whatsappHref(phone: string | null | undefined): string | null {
  const digits = phone ? messengerDigits(phone) : "";

  return digits.length >= 9 ? `https://wa.me/${digits}` : null;
}

/** `https://t.me/+992…` opens a chat by number. */
export function telegramHref(phone: string | null | undefined): string | null {
  const digits = phone ? messengerDigits(phone) : "";

  return digits.length >= 9 ? `https://t.me/+${digits}` : null;
}

/** CPL / CAC: «—» when the API has no number (no leads / nobody enrolled). */
export function moneyOrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";

  return formatPrice(value);
}

export function percentLabel(value: number): string {
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value)}%`;
}

/** `YYYY-MM-DDTHH:mm` (a datetime-local value) of an ISO timestamp, in Asia/Dushanbe. */
export function localInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Dushanbe",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));

  return parts.replace(" ", "T");
}

/** A datetime-local value (Dushanbe wall time, UTC+5, no DST) as an ISO timestamp for the API. */
export function fromLocalInput(value: string): string | null {
  return value ? `${value}:00+05:00` : null;
}
