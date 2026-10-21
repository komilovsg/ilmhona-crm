/** Russian copy of the error screens (404, in-shell error, root fallback): one place, unit-tested. */
export const ERROR_COPY = {
  notFound: {
    code: "404",
    title: "Страница не найдена",
    text: "Такой страницы нет или она была перемещена. Проверьте адрес или вернитесь на главную.",
    home: "На главную",
    back: "Назад",
  },
  failure: {
    title: "Что-то пошло не так",
    text: "Страница не открылась из-за внутренней ошибки. Попробуйте ещё раз; если не помогает, сообщите код в поддержку.",
    retry: "Повторить",
    home: "На главную",
    codeLabel: "Код ошибки",
  },
  fatal: {
    title: "Приложение не загрузилось",
    text: "Произошла серьёзная ошибка. Обновите страницу; если не помогает, сообщите код в поддержку.",
    retry: "Повторить",
    home: "На главную",
    codeLabel: "Код ошибки",
  },
} as const;

/** What support needs: the server digest only (never the message or a stack, in production or not). */
export function errorCode(error: unknown): string | null {
  const digest = (error as { digest?: unknown } | null | undefined)?.digest;
  return typeof digest === "string" && digest.trim() ? digest.trim() : null;
}

/**
 * The code shown to the user: the server digest when there is one; an error thrown in the browser
 * has none, so it gets a short stable hash of its name and message (the text itself is never shown).
 */
export function supportCode(error: unknown): string {
  const digest = errorCode(error);
  if (digest) return digest;
  const e = error as { name?: unknown; message?: unknown } | null | undefined;
  const text = `${String(e?.name ?? "Error")}:${String(e?.message ?? "")}`;
  let h = 0x811c9dc5; // FNV-1a
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193) >>> 0;
  return `E-${h.toString(16).padStart(8, "0").slice(0, 6).toUpperCase()}`;
}
