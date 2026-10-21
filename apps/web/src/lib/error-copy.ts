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
