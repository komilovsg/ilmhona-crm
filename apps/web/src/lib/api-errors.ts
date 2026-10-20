// One Russian text per API error code. tests/test_error_registry.py (API) keeps this list equal
// to the codes the API defines: add the text here when you define a code there.
// Keep one `code: "text",` per line — that test reads this file.
export const apiErrors: Record<string, string> = {
  validation_failed: "Проверьте заполнение полей.",
  internal_error: "Что-то пошло не так. Попробуйте ещё раз.",
  bad_request: "Некорректный запрос.",
  not_found: "Не найдено.",
  method_not_allowed: "Действие недоступно.",
  not_authenticated: "Войдите в систему.",
  forbidden: "Недостаточно прав.",
  csrf_header_missing: "Запрос отклонён. Обновите страницу.",
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
  name_taken: "Такое название уже есть.",
  role_in_use: "Роль назначена пользователям. Сначала смените им роль.",
  role_locked: "Роль «Суперадмин» нельзя менять или удалять.",
  role_system: "Системную роль нельзя удалить.",
};

// Raised by the browser side only (no response from the API).
const clientErrors: Record<string, string> = {
  network_error: "Нет связи с сервером. Проверьте интернет.",
};

export function errorText(code: string | undefined): string {
  return (code && (apiErrors[code] ?? clientErrors[code])) || apiErrors.internal_error;
}
