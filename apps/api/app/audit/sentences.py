"""The audit log in Russian: every entry becomes one readable sentence, here and only here.

    «Каримов Курбон: изменён студент Алиев Алишер — телефон +992900000001 → +992930000002»
    «Каримов Курбон: создан поток G-012» · «Каримов Курбон — вход в систему»

The wording is gender-neutral: the actor is never the subject of a verb («вошёл», «изменила»),
the verb is a passive participle that agrees with the object («создан поток», «создана роль»).
    «Неудачная попытка входа для логина ali» · «Логин ali заблокирован на 15 минут»

`sentence()` is pure: ids in the diff are turned into names through the `names` map the caller
resolves in one batch. A new audited action needs a row in `ACTIONS` (an unknown action still
reads as «Курбон: <action>»), a new field a row in `FIELDS`.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Dushanbe")
MAX_FIELDS = 4

# audit filter «section» -> the entities it covers; `auth` is by action (sign-ins, lockouts)
SECTION_ENTITIES: dict[str, tuple[str, ...]] = {
    "students": ("student",),
    "cohorts": ("cohort", "lesson", "enrollment"),
    "rooms": ("room", "course"),
    "users": ("app_user", "role"),
    "payments": ("payment",),
    "instructors": ("instructor_payout",),
    "leads": ("lead",),
    "marketing": ("campaign",),
    "graduates": ("employment", "graduate", "graduate_course"),
    "master_list": ("master_list",),
    "dashboard": ("dashboard_month",),
}
AUTH_LABEL = "Вход в систему"


def section_of(entity: str, action: str) -> str | None:
    if action.startswith("auth."):
        return "auth"
    for section, entities in SECTION_ENTITIES.items():
        if entity in entities:
            return section
    return None


# action -> (passive verb agreeing with the object, object): «Курбон: <verb> <object> <label>»
ACTIONS: dict[str, tuple[str, str]] = {
    "demo.seed": ("загружены", "демо-данные"),
    "demo.wipe": ("удалены", "демо-данные"),
    "student.create": ("создан", "студент"),
    "student.update": ("изменён", "студент"),
    "student.delete": ("удалён", "студент"),
    "cohort.create": ("создан", "поток"),
    "cohort.update": ("изменён", "поток"),
    "cohort.delete": ("удалён", "поток"),
    "cohort.cancel": ("отменён", "поток"),
    "cohort.restore": ("восстановлен", "поток"),
    "room.create": ("создана", "аудитория"),
    "room.update": ("изменена", "аудитория"),
    "room.delete": ("удалена", "аудитория"),
    "course.create": ("создан", "курс"),
    "course.update": ("изменён", "курс"),
    "course.delete": ("удалён", "курс"),
    "user.create": ("создан", "пользователь"),
    "user.update": ("изменён", "пользователь"),
    "user.delete": ("удалён", "пользователь"),
    "user.activate": ("активирован", "пользователь"),
    "user.reset_password": ("сброшен", "пароль пользователя"),
    "user.deactivate": ("заблокирован", "пользователь"),
    "user.session_end": ("завершён сеанс", "пользователя"),
    "user.reset_rejected": ("отклонён запрос на сброс пароля", "пользователя"),
    "role.create": ("создана", "роль"),
    "role.update": ("изменена", "роль"),
    "role.delete": ("удалена", "роль"),
    "lesson.create": ("добавлен", "урок потока"),
    "lesson.move": ("перенесён", "урок потока"),
    "lesson.cancel": ("отменён", "урок потока"),
    "payment.create": ("создана", "оплата"),
    "payment.update": ("изменена", "оплата"),
    "payment.delete": ("удалена", "оплата"),
    "payment.confirm": ("подтверждена", "оплата"),
    "payment.unconfirm": ("снято подтверждение", "оплаты"),
    "payout.create": ("отмечена", "выплата"),
    "payout.update": ("изменена", "выплата"),
    "payout.delete": ("удалена", "выплата"),
    "lead.create": ("создан", "лид"),
    "lead.update": ("изменён", "лид"),
    "lead.delete": ("удалён", "лид"),
    "campaign.create": ("создана", "кампания"),
    "campaign.update": ("изменена", "кампания"),
    "campaign.delete": ("удалена", "кампания"),
    "employment.create": ("добавлено", "трудоустройство"),
    "employment.update": ("изменено", "трудоустройство"),
    "employment.delete": ("удалено", "трудоустройство"),
}
# creations that also read their values: «создана оплата … — сумма 500 TJS, способ alif»
WITH_VALUES = {"payment.create", "payout.create"}

# table (the `entity` of an `export` entry) -> Russian name
TABLES: dict[str, str] = {
    "app_user": "пользователи",
    "role": "роли и права",
    "audit_log": "журнал",
    "room": "аудитории",
    "course": "курсы",
    "lesson": "расписание",
    "cohort": "потоки",
    "enrollment": "студенты потока",
    "student": "студенты",
    "payment": "оплаты",
    "debtor": "должники",
    "salary": "график выплат",
    "instructor_payout": "выплаты",
    "instructor": "инструкторы",
    "lead": "лиды",
    "campaign": "кампании",
    "master_list": "мастер-лист",
    "graduate": "выпускники",
    "graduate_course": "выпускники по курсам",
    "employment": "трудоустройство",
    "dashboard_month": "дашборд по месяцам",
    "grade": "оценки потока",
    "today": "сегодня и не заполнено",
    "student_card": "карточка студента",
    "reset_request": "запросы пароля",
}
FILTERS = {
    "q": "поиск",
    "section": "раздел",
    "date_from": "с",
    "date_to": "по",
    "since": "с",
    "until": "по",
    "user_id": "пользователь",
    "is_active": "активен",
    "cohort": "поток",
    "entity": "объект",
    "entity_id": "ID объекта",
    "action": "действие",
    "status": "статус",
    "method": "способ",
    "month": "месяц",
    "instructor_id": "инструктор",
    "student": "студент",
}
MONEY = {
    "default_price_month",
    "price_month",
    "amount",
    "default_rate",
    "instructor_rate",
    "budget",
}

FIELDS: dict[str, str] = {
    "login": "логин",
    "full_name": "ФИО",
    "phone": "телефон",
    "email": "email",
    "gender": "пол",
    "branch_id": "филиал",
    "role_id": "роль",
    "is_active": "активен",
    "name": "название",
    "capacity": "вместимость",
    "direction": "направление",
    "default_price_month": "цена в месяц",
    "duration_months": "длительность, мес.",
    "format": "формат",
    "code": "код",
    "course_id": "курс",
    "instructor_id": "инструктор",
    "room_id": "аудитория",
    "start_date": "начало",
    "end_date": "окончание",
    "weekdays": "дни недели",
    "start_time": "время начала",
    "end_time": "время окончания",
    "price_month": "цена в месяц",
    "status": "статус",
    "date": "дата",
    "start": "начало",
    "end": "конец",
    "cancelled": "отменён",
    "expires_at": "временный пароль до",
    "lessons": "уроки",
    "homework": "Д/З",
    "final": "финал",
    "month_no": "месяц",
    "amount": "сумма",
    "method": "способ",
    "paid_at": "дата оплаты",
    "note": "заметка",
    "default_rate": "ставка по умолчанию",
    "instructor_rate": "ставка инструктора",
    "source": "источник",
    "campaign_id": "кампания",
    "call_status": "статус звонка",
    "next_contact_at": "перезвонить",
    "refusal_reason": "причина отказа",
    "comment": "комментарий",
    "needs_review": "нужна проверка",
    "budget": "бюджет",
    "platform": "платформа",
    "organization": "организация",
    "position": "должность",
    "employed_at": "дата трудоустройства",
    "reason": "причина",
}
REFS = {"branch_id", "role_id", "instructor_id", "room_id", "course_id", "user_id", "campaign_id"}
DAYS = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
VALUES = {
    "male": "мужской",
    "female": "женский",
    "offline": "очно",
    "online": "онлайн",
    "view": "просмотр",
    "change": "изменение",
}
NONE = "—"
_PRESENCE: dict[Any, str] = {None: "не отмечено", True: "присутствует", False: "отсутствует"}


@dataclass
class Entry:
    actor: str | None
    action: str
    entity: str
    label: str | None
    diff: dict[str, Any]


def _date(value: str) -> str:
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).strftime("%d.%m.%Y")
        if "T" in value:
            return datetime.fromisoformat(value).astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        pass
    return value


def value_text(field: str, value: Any, names: dict[str, str]) -> str:
    if value is None or value == "":
        return NONE
    if isinstance(value, bool):
        return "да" if value else "нет"
    if field in REFS and isinstance(value, str):
        return names.get(value, "удалён")
    if field == "weekdays" and isinstance(value, list):
        return ", ".join(DAYS.get(d, str(d)) for d in value)
    if isinstance(value, list):
        return ", ".join(value_text(field, v, names) for v in value)
    if isinstance(value, str):
        return VALUES.get(value) or _date(value)
    return str(value)


def _money(value: Any) -> str:
    """`500.00` -> `500`, `1234.5` -> `1 234,50`: money reads the same in every diff."""
    if value is None or value == "":
        return NONE
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    text = f"{d:.0f}" if d == d.to_integral() else f"{d:.2f}"
    whole, _, kopecks = text.partition(".")
    whole = f"{int(whole):,}".replace(",", " ")
    return f"{whole},{kopecks}" if kopecks else whole


def _pair(change: Any) -> tuple[Any, Any]:
    if isinstance(change, list) and len(change) == 2:
        return change[0], change[1]
    return None, change


def changes(diff: dict[str, Any], names: dict[str, str], sections: dict[str, str]) -> list[str]:
    """«телефон +992… → +992…» pieces of a diff, the role matrix as «Раздел: нет → просмотр»."""
    out: list[str] = []
    for field, change in diff.items():
        if field == "permissions" and isinstance(change, dict):
            for section, perm in change.items():
                old, new = _pair(perm)
                out.append(
                    f"права «{sections.get(section, section)}»: "
                    f"{VALUES.get(old, NONE) if old else 'нет'} → "
                    f"{VALUES.get(new, NONE) if new else 'нет'}"
                )
            continue
        old, new = _pair(change)
        if field == "future_lessons":
            out.append(f"будущие уроки: удалено {old}, создано {new}")
            continue
        if field in MONEY:
            out.append(f"{FIELDS[field]} {_money(old)} → {_money(new)} TJS")
            continue
        out.append(
            f"{FIELDS.get(field, field)} {value_text(field, old, names)} → "
            f"{value_text(field, new, names)}"
        )
    return out


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _tail(label: str | None) -> str:
    return f" {label}" if label else ""


def _pieces(label: str | None) -> tuple[str, str]:
    """`Алиев Алишер (G-012)` -> student, cohort."""
    if label and label.endswith(")") and " (" in label:
        student, cohort = label[:-1].rsplit(" (", 1)
        return student, cohort
    return label or NONE, NONE


def _with_changes(
    head: str, diff: dict[str, Any], names: dict[str, str], sec: dict[str, str]
) -> str:
    parts = changes(diff, names, sec)
    if not parts:
        return head
    shown = "; ".join(parts[:MAX_FIELDS])
    more = len(parts) - MAX_FIELDS
    return f"{head} — {shown}" + (f" и ещё {more}" if more > 0 else "")


def sentence(
    e: Entry, names: dict[str, str] | None = None, sections: dict[str, str] | None = None
) -> str:
    names, sections = names or {}, sections or {}
    who = e.actor or "Система"
    a, lab = e.action, e.label

    if a == "auth.login_failed":
        return f"Неудачная попытка входа для логина {lab}"
    if a == "auth.locked":
        _, minutes = _pair(e.diff.get("minutes"))
        n = int(minutes or 15)
        return f"Логин {lab} заблокирован на {n} {_plural(n, 'минуту', 'минуты', 'минут')}"
    if a == "auth.login":
        return f"{who} — вход в систему"
    if a == "auth.reset_requested":
        return f"Запрос на сброс пароля для логина {lab}"
    if a == "auth.session_end":
        return f"{who} — завершён сеанс на одном из устройств"
    if a == "auth.session_end_others":
        _, n = _pair(e.diff.get("count"))
        return f"{who} — завершены сеансы на других устройствах: {n}"
    if a == "auth.change_password":
        return f"{who} — смена пароля"
    if a == "profile.update":
        return _with_changes(f"{who}: изменены данные своего профиля", e.diff, names, sections)
    if a == "export":
        table = TABLES.get(e.entity, e.entity)
        _, rows = _pair(e.diff.get("rows"))
        n = int(rows or 0)
        _, filters = _pair(e.diff.get("filters"))
        head = f"{who} — выгрузка в Excel: {table}, {n} {_plural(n, 'строка', 'строки', 'строк')}"
        shown = (
            ", ".join(
                f"{FILTERS.get(k, FIELDS.get(k, k))} {value_text(k, v, names)}"
                for k, v in filters.items()
            )
            if isinstance(filters, dict)
            else ""
        )
        return f"{head} (фильтры: {shown})" if shown else head

    if a == "import.apply":
        counts = [
            f"{what} {_pair(e.diff.get(key))[1]}"
            for key, what in (
                ("student", "студентов"),
                ("enrollment", "зачислений"),
                ("payment", "оплат"),
                ("lead", "лидов"),
            )
            if _pair(e.diff.get(key))[1]
        ]
        tail = f" — {', '.join(counts)}" if counts else ""
        return f"{who}: выполнен перенос из старой системы{tail}"
    if a == "enrollment.create":
        student, cohort = _pair(e.diff.get("student"))[1], _pair(e.diff.get("cohort"))[1]
        return f"{who}: зачислен студент {student} в поток {cohort}"
    if a == "enrollment.delete":
        student, cohort = _pair(e.diff.get("student"))[0], _pair(e.diff.get("cohort"))[0]
        lost = []
        marks = _pair(e.diff.get("lost_marks"))[0]
        if marks:
            lost.append(f"отметок посещаемости: {marks}")
        if _pair(e.diff.get("lost_grade"))[0]:
            lost.append("оценки")
        if cert := _pair(e.diff.get("lost_certificate"))[0]:
            lost.append(f"сертификат {cert}")
        tail = f"; потеряно: {', '.join(lost)}" if lost else ""
        return f"{who}: студент {student} убран из потока {cohort}{tail}"
    if a == "enrollment.certificate":
        student, cohort = _pieces(lab)
        _, number = _pair(e.diff.get("certificate_no"))
        return f"{who}: выдан сертификат {number} студенту {student} (поток {cohort})"
    if a.startswith("employment."):
        # an update's diff has no «student»: the label (the student's name) names them
        student = _pair(e.diff.get("student"))[0 if a.endswith("delete") else 1] or lab
        verb, _ = ACTIONS[a]
        diff = {k: v for k, v in e.diff.items() if k != "student"}
        return _with_changes(
            f"{who}: {verb} трудоустройство студента {student}", diff, names, sections
        )
    if a == "enrollment.update":
        student, cohort = _pieces(lab)
        diff = {k: v for k, v in e.diff.items() if k != "cohort"}
        return _with_changes(
            f"{who}: изменено зачисление студента {student} в потоке {cohort}",
            diff,
            names,
            sections,
        )
    if a == "cohort.close_enrollments":
        _, n = _pair(e.diff.get("enrollments_completed"))
        _, grads = _pair(e.diff.get("graduates"))
        tail = f", из них выпускников: {grads}" if grads else ""
        return f"{who}: поток {lab} закончился, зачислений завершено: {n}{tail}"
    if a == "lead.convert":
        student = _pair(e.diff.get("student"))[1]
        _, new = _pair(e.diff.get("student_new"))
        how = "создан новый студент" if new else "найден студент по телефону"
        return f"{who}: лид {lab} записан — {how} {student}"
    if a == "lead.import":
        _, n = _pair(e.diff.get("created"))
        _, review = _pair(e.diff.get("needs_review"))
        tail = f", из них на проверку: {review}" if review else ""
        return f"{who}: импортировано лидов из CSV: {n}{tail}"
    if a == "grade.update":
        student, cohort = _pieces(lab)
        return _with_changes(
            f"{who}: оценки студента {student} в потоке {cohort}", e.diff, names, sections
        )
    if a == "attendance.mark":
        code, _, day = (lab or "").partition(", ")
        student = _pair(e.diff.get("student"))[1]
        old, new = _pair(e.diff.get("present"))
        _, reason = _pair(e.diff.get("reason"))
        head = (
            f"{who}: посещаемость {student} ({code}, {day}) — {_PRESENCE[old]} → {_PRESENCE[new]}"
        )
        return head + (f", причина: {reason}" if reason else "")
    if a == "attendance.import":
        _, marks = _pair(e.diff.get("marks"))
        _, lessons = _pair(e.diff.get("lessons"))
        _, over = _pair(e.diff.get("overwritten"))
        tail = f", перезаписано: {over}" if over else ""
        head = f"{who}: импорт посещаемости {lab}"
        return f"{head} — {marks or 0} отметок, {lessons or 0} уроков добавлено{tail}"
    if a == "attendance.mark_all":
        code, _, day = (lab or "").partition(", ")
        _, n = _pair(e.diff.get("marked"))
        return f"{who}: урок {code} за {day} — все присутствуют, отмечено: {n}"

    if a.startswith("lesson.") and a in ACTIONS:
        verb, what = ACTIONS[a]
        code, _, day = (lab or "").partition(", ")
        head = f"{who}: {verb} {what} {code}" + (f" за {day}" if day else "")
        if a != "lesson.move":
            return head
        return _with_changes(
            head, {k: v for k, v in e.diff.items() if k != "cancelled"}, names, sections
        )

    if a in ACTIONS:
        verb, what = ACTIONS[a]
        head = f"{who}: {verb} {what}{_tail(lab)}"
        with_changes = a.endswith(".update") or a in WITH_VALUES
        return _with_changes(head, e.diff, names, sections) if with_changes else head
    return f"{who}: {a}{_tail(lab)}"
