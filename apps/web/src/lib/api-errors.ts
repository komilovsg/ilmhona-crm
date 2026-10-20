// One Russian text per API error code. tests/test_error_registry.py (API) keeps this list equal
// to the codes the API defines: add the text here when you define a code there.
// Keep one `code: "text",` per line — that test reads this file.
export const apiErrors: Record<string, string> = {
  validation_failed: "Проверьте заполнение полей.",
  export_too_large: "Слишком много строк для Excel (больше 50 000). Сузьте фильтры.",
  internal_error: "Что-то пошло не так. Попробуйте ещё раз.",
  bad_request: "Некорректный запрос.",
  not_found: "Не найдено.",
  method_not_allowed: "Действие недоступно.",
  not_authenticated: "Войдите в систему.",
  forbidden: "Недостаточно прав.",
  csrf_header_missing: "Запрос отклонён. Обновите страницу.",
  proxy_required: "Запрос отклонён. Обновите страницу.",
  invalid_credentials: "Неверный логин или пароль.",
  too_many_attempts: "Слишком много попыток входа. Подождите 15 минут.",
  temp_password_expired: "Срок временного пароля истёк. Попросите администратора выдать новый.",
  password_change_required: "Сначала смените временный пароль.",
  wrong_password: "Текущий пароль неверный.",
  weak_password: "Пароль: 8–72 символа, буква, цифра и спецсимвол.",
  same_password: "Новый пароль должен отличаться от текущего.",
  login_taken: "Такой логин уже занят.",
  phone_taken: "Такой телефон уже указан у другого пользователя.",
  role_not_assignable: "Нельзя выдавать или менять роль с правами выше ваших.",
  branch_forbidden: "Это вне вашего филиала.",
  cannot_deactivate_self: "Нельзя заблокировать или удалить самого себя.",
  last_superadmin: "Нельзя оставить систему без активного суперадмина.",
  user_in_use: "Пользователь связан с данными. Деактивируйте его вместо удаления.",
  concurrent_change: "Данные только что изменил другой пользователь. Повторите.",
  stale_version: "Запись только что изменил другой пользователь. Данные обновлены, повторите.",
  version_required: "Обновите страницу и повторите.",
  course_global_only: "Курсы общие для филиалов: их меняют только сотрудники без привязки к филиалу.",
  name_taken: "Такое название уже есть.",
  role_in_use: "Роль назначена пользователям. Сначала смените им роль.",
  role_locked: "Роль «Суперадмин» нельзя менять или удалять.",
  role_system: "Системную роль нельзя удалить.",
  room_name_taken: "Аудитория с таким названием уже есть в этом филиале.",
  course_name_taken: "Курс с таким названием уже есть.",
  room_in_use: "В аудитории есть потоки или уроки. Удалить нельзя.",
  course_in_use: "По курсу есть потоки. Удалить нельзя.",
  cohort_in_use: "В потоке есть студенты. Сначала уберите их или отмените поток.",
  student_in_use: "Студент зачислен в потоки. Удалить нельзя.",
  room_busy: "Аудитория занята потоком {cohort}: {date}, {start}–{end}.",
  already_enrolled: "Студент уже зачислен в этот поток.",
  cohort_full: "В потоке нет свободных мест.",
  cohort_closed: "Поток завершён или отменён, изменить его нельзя.",
  cohort_not_cancelled: "Поток не отменён.",
  lesson_cancelled: "Урок отменён.",
  enrolled_after_lesson: "Студент зачислен позже этого урока: отметка невозможна.",
  instructor_invalid: "Инструктор должен быть активным сотрудником с ролью «Инструктор» из этого филиала.",
  room_branch_mismatch: "Аудитория из другого филиала.",
  student_branch_mismatch: "Студент из другого филиала.",
};

// Raised by the browser side only (no response from the API).
const clientErrors: Record<string, string> = {
  network_error: "Нет связи с сервером. Проверьте интернет.",
};

/** The text of an error code; `{name}` placeholders are filled from the problem's `params`. */
export function errorText(code: string | undefined, params?: Record<string, unknown>): string {
  const text = (code && (apiErrors[code] ?? clientErrors[code])) || apiErrors.internal_error;

  return text.replace(/\{(\w+)\}/g, (_, key: string) => String(params?.[key] ?? ""));
}
