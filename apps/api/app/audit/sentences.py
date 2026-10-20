"""The audit log in Russian: every entry becomes one readable sentence, here and only here.

    «Курбон изменил студента Алиев Алишер: телефон +992900000001 → +992930000002»
    «Курбон создал поток G-012» · «Курбон вошёл в систему»
    «Неудачная попытка входа для логина ali» · «Логин ali заблокирован на 15 минут»

`sentence()` is pure: ids in the diff are turned into names through the `names` map the caller
resolves in one batch. A new audited action needs a row in `ACTIONS` (an unknown action still
reads as «Курбон: <action>»), a new field a row in `FIELDS`.
"""

from dataclasses import dataclass
from datetime import datetime
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
}
AUTH_LABEL = "Вход в систему"


def section_of(entity: str, action: str) -> str | None:
    if action.startswith("auth."):
        return "auth"
    for section, entities in SECTION_ENTITIES.items():
        if entity in entities:
            return section
    return None


# action -> (verb, what), «Курбон <verb> <what> <label>»
ACTIONS: dict[str, tuple[str, str]] = {
    "student.create": ("создал", "студента"),
    "student.update": ("изменил", "студента"),
    "student.delete": ("удалил", "студента"),
    "cohort.create": ("создал", "поток"),
    "cohort.update": ("изменил", "поток"),
    "cohort.delete": ("удалил", "поток"),
    "cohort.cancel": ("отменил", "поток"),
    "cohort.restore": ("восстановил", "поток"),
    "room.create": ("создал", "аудиторию"),
    "room.update": ("изменил", "аудиторию"),
    "room.delete": ("удалил", "аудиторию"),
    "course.create": ("создал", "курс"),
    "course.update": ("изменил", "курс"),
    "course.delete": ("удалил", "курс"),
    "user.create": ("создал", "пользователя"),
    "user.update": ("изменил", "пользователя"),
    "user.delete": ("удалил", "пользователя"),
    "user.activate": ("активировал", "пользователя"),
    "user.reset_password": ("сбросил пароль", "пользователю"),
    "user.deactivate": ("заблокировал", "пользователя"),
    "role.create": ("создал", "роль"),
    "role.update": ("изменил", "роль"),
    "role.delete": ("удалил", "роль"),
    "lesson.create": ("добавил", "урок потока"),
    "lesson.move": ("перенёс", "урок потока"),
    "lesson.cancel": ("отменил", "урок потока"),
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
}
REFS = {"branch_id", "role_id", "instructor_id", "room_id", "course_id", "user_id"}
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
    return f"{head}: {shown}" + (f" и ещё {more}" if more > 0 else "")


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
        return f"{who} вошёл в систему"
    if a == "auth.change_password":
        return f"{who} сменил пароль"
    if a == "profile.update":
        return _with_changes(f"{who} изменил свой профиль", e.diff, names, sections)

    if a == "enrollment.create":
        student, cohort = _pair(e.diff.get("student"))[1], _pair(e.diff.get("cohort"))[1]
        return f"{who} зачислил студента {student} в поток {cohort}"
    if a == "enrollment.delete":
        student, cohort = _pair(e.diff.get("student"))[0], _pair(e.diff.get("cohort"))[0]
        return f"{who} убрал студента {student} из потока {cohort}"
    if a == "enrollment.update":
        student, cohort = _pieces(lab)
        diff = {k: v for k, v in e.diff.items() if k != "cohort"}
        return _with_changes(
            f"{who} изменил зачисление студента {student} в потоке {cohort}", diff, names, sections
        )
    if a == "cohort.close_enrollments":
        _, n = _pair(e.diff.get("enrollments_completed"))
        return f"{who}: поток {lab} закончился, зачислений завершено: {n}"

    if a.startswith("lesson.") and a in ACTIONS:
        verb, what = ACTIONS[a]
        code, _, day = (lab or "").partition(", ")
        head = f"{who} {verb} {what} {code}" + (f" за {day}" if day else "")
        if a != "lesson.move":
            return head
        return _with_changes(
            head, {k: v for k, v in e.diff.items() if k != "cancelled"}, names, sections
        )

    if a in ACTIONS:
        verb, what = ACTIONS[a]
        head = f"{who} {verb} {what}{_tail(lab)}"
        return _with_changes(head, e.diff, names, sections) if a.endswith(".update") else head
    return f"{who}: {a}{_tail(lab)}"
