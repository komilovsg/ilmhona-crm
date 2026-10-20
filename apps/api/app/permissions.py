"""Sections and levels of the rights matrix (SPEC «Права»).

Levels: none (no row) < view < change. `change` also covers delete: there is no separate
delete level. Superadmin (role code `superadmin`) is allowed everything, also sections added later.
"""

from typing import Literal

Level = Literal["view", "change"]
LEVELS: tuple[Level, ...] = ("view", "change")
_RANK = {"view": 1, "change": 2}

# key -> Russian label. Keys are stored in the DB (role_permission.section): never rename one,
# add a migration that widens the CHECK constraint when a section is added.
SECTIONS: dict[str, str] = {
    "dashboard": "Дашборд",
    "leads": "Лиды",
    "students": "Студенты",
    "cohorts": "Потоки",
    "attendance": "Посещаемость и оценки",
    "payments": "Оплаты",
    "rooms": "Аудитории",
    "graduates": "Выпускники и трудоустройство",
    "master_list": "Мастер-лист",
    "marketing": "Маркетинг",
    "instructors": "Инструкторы и зарплаты",
    "users": "Пользователи и роли",
    "audit": "Журнал",
}

SUPERADMIN_CODE = "superadmin"

# Starting rights of the seeded roles (editable by the superadmin except Суперадмин).
MANAGER_DEFAULT: dict[str, Level] = {
    "dashboard": "view",
    "leads": "change",
    "students": "change",
    "cohorts": "change",
    "attendance": "view",
    "payments": "change",
    "rooms": "change",
    "graduates": "view",
    "master_list": "view",
    "marketing": "view",
}
INSTRUCTOR_DEFAULT: dict[str, Level] = {
    "cohorts": "view",
    "attendance": "change",
    "instructors": "view",
}


def rank(level: str | None) -> int:
    return _RANK.get(level or "", 0)


def allows(have: str | None, need: str) -> bool:
    return rank(have) >= rank(need)
