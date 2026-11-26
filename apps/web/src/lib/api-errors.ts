import { fullDate } from "./education.ts";

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
  weak_password: "Пароль не соответствует правилам.",
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
  enrollment_not_yours: "Инструктор может удалить только студентов, которых добавил сам.",
  enrollment_has_records: "У студента уже есть оплаты, отметки, оценки или трудоустройство, либо менеджер сменил его статус — удалить нельзя. Обратитесь к менеджеру.",
  room_busy: "Аудитория занята потоком {cohort}: {date}, {start}–{end}.",
  instructor_busy: "Инструктор в это время ведёт урок: поток {cohort}, {date}, {start}–{end}.",
  already_enrolled: "Студент уже зачислен в этот поток.",
  cohort_closed: "Поток завершён или отменён, изменить его нельзя.",
  cohort_not_cancelled: "Поток не отменён.",
  cohort_not_active: "Завершить можно только активный поток.",
  cohort_not_done: "Поток не завершён.",
  finish_changed: "Состав выпускников изменился: проверьте новые числа и подтвердите ещё раз.",
  lesson_cancelled: "Урок отменён.",
  lesson_not_held: "Урок ещё впереди: отметить можно с дня урока.",
  enrolled_after_lesson: "Студент зачислен позже этого урока: отметка невозможна.",
  instructor_invalid: "Инструктор должен быть активным сотрудником с ролью «Инструктор» из этого филиала.",
  room_branch_mismatch: "Аудитория из другого филиала.",
  student_branch_mismatch: "Студент из другого филиала.",
  payment_month_invalid: "В потоке {months} мес.: такого месяца нет.",
  month_already_paid: "Месяц {month_no} уже оплачен: {paid} TJS.",
  month_overpaid: "За месяц {month_no} осталось оплатить {remaining} TJS.",
  payment_confirmed: "Подтверждённую оплату нельзя менять или удалять. Сначала снимите подтверждение.",
  idempotency_key_reused: "Эта оплата уже сохранена с другими данными. Обновите форму и повторите.",
  enrollment_has_payments: "У зачисления есть оплаты. Убрать студента из потока нельзя.",
  cohort_no_instructor: "У потока нет инструктора.",
  discount_reason_required: "Укажите причину скидки в заметке.",
  discount_no_price: "У потока не указана цена: скидку не от чего считать.",
  month_discount_exists: "За месяц {month_no} скидка уже дана: {percent}%.",
  payment_amount_zero: "Сумма 0 — только при скидке 100%.",
  payout_period_invalid: "Поток в этом месяце не идёт.",
  payout_exists: "За этот месяц по этому потоку выплата уже отмечена.",
  lead_converted: "Лид уже записан студентом: его статус не меняется.",
  lead_use_convert: "Статус «записан» ставится кнопкой «Записать в поток».",
  campaign_branch_mismatch: "Кампания из другого филиала, чем лид.",
  campaign_in_use: "У кампании есть лиды. Удалить нельзя.",
  campaign_dates_invalid: "Дата окончания раньше даты старта.",
  goal_dates_invalid: "Срок должен быть позже даты начала.",
  import_too_large: "Файл слишком большой (больше 2 МБ).",
  import_too_many_rows: "В файле больше {limit} строк. Разделите его на части.",
  import_unreadable: "Не удалось прочитать файл. Нужен Excel (.xlsx) или CSV.",
  import_no_rows: "В файле нет строк для импорта.",
  journal_no_dates: "Не нашли строку с датами уроков. Укажите её номер вручную.",
  journal_no_names: "Не нашли колонку с ФИО. Укажите её вручную.",
  import_mapping_invalid: "Выберите колонку с именем или с телефоном.",
  not_graduate: "Сертификат и трудоустройство — только у выпускника.",
  certificate_issued: "Сертификат уже выдан: статус «выпускник» не меняется.",
  employment_enrollment_mismatch: "Это зачисление другого студента.",
  grading_scheme_invalid: "Шкала оценок не сходится: {problems}.",
  grading_scores_archived: "У удаляемых категорий есть оценки: они сохранятся в архиве. Подтвердите удаление.",
  cert_field_unknown: "В шаблоне неизвестное поле «{field}».",
  cert_layout_invalid: "Макет шаблона заполнен неверно.",
  cert_asset_invalid: "Изображение не подходит: нужен PNG или JPEG до 8 МБ с заметной подписью или печатью.",
  cert_asset_dimensions: "Изображение слишком большое: сторона не должна быть больше {side_px} px.",
  cert_asset_missing: "Изображение шаблона не найдено.",
  cert_gender_missing: "У студента не указан пол: шаблон требует его.",
  cert_text_overflow: "Текст не помещается в блок шаблона.",
  cert_render_timeout: "Сертификат формируется слишком долго. Повторите позже.",
  cert_pdf_too_large: "Файл сертификата слишком большой.",
  cert_not_issued: "Номер сертификата ещё не выдан.",
  cert_no_template: "Нет опубликованного шаблона сертификата.",
  cert_template_name_taken: "Шаблон с таким названием уже есть.",
  cert_nothing_to_publish: "Нечего публиковать: черновик совпадает с последней версией.",
  cert_rule_duplicate: "Для этого курса и инструктора правило уже есть.",
  cert_rule_invalid: "В правиле указан несуществующий курс, инструктор или неактивный шаблон.",
  cert_already_issued: "Сертификат этому студенту уже выдан.",
  cert_not_ready: "Часть студентов не готова к выдаче сертификата.",
  cert_not_valid: "Сертификат уже заменён или отозван.",
  cohort_not_finished: "Сертификаты выдаются только после завершения потока.",
  cert_comment_required: "Укажите комментарий.",
  cert_custom_invalid: "Значение поля сертификата заполнено неверно.",
  cert_director_overflow: "Имя или должность директора не помещаются в шаблон.",
  cohort_not_completed: "Поток ещё не завершён: статусы выпускников определятся при завершении.",
};

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

// Raised by the browser side only (no response from the API).
const clientErrors: Record<string, string> = {
  network_error: "Нет связи с сервером. Проверьте интернет.",
  check_marked_fields: "Проверьте выделенные поля.",
};

/** The text of an error code; `{name}` placeholders are filled from the problem's `params`. */
export function errorText(code: string | undefined, params?: Record<string, unknown>): string {
  const text = (code && (apiErrors[code] ?? clientErrors[code])) || apiErrors.internal_error;

  return text.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = params?.[key];

    if (Array.isArray(value)) return value.join("; ");
    // a day arrives as ISO (2026-11-17), people read 17.11.2026
    return typeof value === "string" && ISO_DAY.test(value) ? fullDate(value) : String(value ?? "");
  });
}

/** The hint under one form field for a 422 entry (`code` + the limits pydantic gave in `ctx`). */
export function fieldText(code: string, ctx?: Record<string, unknown>): string {
  const num = (key: string) => String(ctx?.[key] ?? "");

  if (code === "missing") return "Обязательное поле";
  if (code === "string_too_long") return `Не длиннее ${num("max_length")} символов`;
  if (code === "string_too_short" || code === "too_short")
    return Number(ctx?.min_length) > 1 ? `Не короче ${num("min_length")} символов` : "Заполните поле";
  if (code === "discount_reason_required") return "Укажите причину скидки";
  if (code === "payment_amount_zero") return "Больше 0 (сумма 0 — только при скидке 100%)";
  if (code === "discount_no_price") return "У потока нет цены";
  if (code === "deadline_before_start") return "Срок должен быть позже начала";
  if (code === "percent_over_100") return "От 1 до 100";
  if (code === "target_not_above_baseline") return "План должен быть больше стартового значения";
  if (code === "invalid_phone") return "Неверный номер. Пример: +992 90 123 45 67";
  if (code === "decimal_max_digits" || code === "decimal_whole_digits") return "Слишком большое число";
  if (code === "decimal_max_places") return "Слишком много знаков после запятой";
  if (/^(int|float|decimal)_(parsing|type)|^decimal_/.test(code)) return "Введите число";
  if (code === "greater_than_equal") return `Не меньше ${num("ge")}`;
  if (code === "less_than_equal") return `Не больше ${num("le")}`;
  if (code === "greater_than") return `Больше ${num("gt")}`;
  if (code === "less_than") return `Меньше ${num("lt")}`;
  if (/^uuid_|^literal_error$|^enum$/.test(code)) return "Выберите значение из списка";
  if (/^time_/.test(code)) return "Неверное время";
  if (/^(date|datetime)_/.test(code)) return "Неверная дата";
  if (code.includes("email")) return "Неверный email";

  return "Неверное значение";
}
