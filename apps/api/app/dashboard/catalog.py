"""The dashboard's cards: which exist, who may be offered which, and the default layout per role.

Hiding a card is cosmetic. The catalog only decides what the customise panel offers and what the
page asks for; every card's endpoint checks the rights itself. A card the user may not read is
never offered, and ids the user may not have are dropped from a saved layout.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.auth.deps import Principal
from app.education.scope import is_instructor
from app.permissions import allows


def sees(*sections: str) -> Callable[[Principal], bool]:
    return lambda p: all(allows(p.level(s), "view") for s in sections)


def sees_any(*sections: str) -> Callable[[Principal], bool]:
    return lambda p: any(allows(p.level(s), "view") for s in sections)


@dataclass(frozen=True)
class Card:
    id: str
    title: str
    offered: Callable[[Principal], bool]


CARDS: tuple[Card, ...] = (
    Card("academy_goal", "Цель академии", lambda p: True),
    Card("month_hero", "Месяц одной фразой", sees("payments")),
    Card("goals", "Цели", lambda p: p.is_superadmin),
    Card("demand", "Спрос на курсы", sees("leads")),
    Card("timeline", "Лента наборов", sees("cohorts")),
    Card("attention", "Требует внимания", sees("dashboard")),
    Card("branches_months", "Филиалы по месяцам", sees("payments")),
    Card("courses_income", "Доход по курсам", sees("dashboard", "payments")),
    Card("notes", "Мои заметки", lambda p: p.is_superadmin),
    Card("queues", "Очереди на сегодня", sees_any("leads", "payments")),
    Card("call_queue", "Очередь звонков", sees("leads")),
    Card("seats", "Наборы: свободные места", sees("cohorts")),
    Card("week", "Неделя", sees("dashboard")),
    Card("overview", "Показатели", sees("dashboard")),
)
BY_ID = {c.id: c for c in CARDS}

# default order per layout; (id, visible). Cards of the catalog that a layout does not list come
# after them, hidden: the user can switch them on.
DEFAULTS: dict[str, tuple[tuple[str, bool], ...]] = {
    "admin": (
        ("academy_goal", True),
        ("month_hero", True),
        ("goals", True),
        ("demand", True),
        ("timeline", True),
        ("attention", True),
        ("branches_months", True),
        ("courses_income", True),
        ("overview", True),
        ("notes", True),
    ),
    "manager": (
        ("academy_goal", True),
        ("queues", True),
        ("call_queue", True),
        ("seats", True),
        ("week", True),
    ),
}


def layout_of(p: Principal) -> str:
    return "admin" if p.is_superadmin else "manager"


def available(p: Principal) -> list[Card]:
    """Cards this user may be offered (an instructor has no dashboard at all)."""
    if is_instructor(p):
        return []
    return [c for c in CARDS if c.offered(p)]


def default_layout(p: Principal) -> list[tuple[str, bool]]:
    cards = available(p)
    have = {c.id for c in cards}
    listed = [(i, v) for i, v in DEFAULTS[layout_of(p)] if i in have]
    seen = {i for i, _ in listed}
    return listed + [(c.id, False) for c in cards if c.id not in seen]


def _ids(value: object) -> list[str]:
    return [i for i in value if isinstance(i, str)] if isinstance(value, list) else []


def resolve(p: Principal, stored: dict[str, Any]) -> list[dict[str, Any]]:
    """The layout to show: the saved order and hidden set (ids the user may not have, or that no
    longer exist, are ignored), then cards the save does not know yet with their default."""
    default = default_layout(p)
    allowed = {i for i, _ in default}
    order = [i for i in dict.fromkeys(_ids(stored.get("order"))) if i in allowed]
    hidden = set(_ids(stored.get("hidden")))
    if order:
        out = [(i, i not in hidden) for i in order]
        out += [(i, v) for i, v in default if i not in set(order)]
    else:
        out = default
    return [{"id": i, "title": BY_ID[i].title, "visible": v} for i, v in out]


def clean(p: Principal, order: list[str], hidden: list[str]) -> dict[str, Any]:
    """What to store: a complete layout over the cards the user may have."""
    have = {c.id for c in available(p)}
    ordered = [i for i in dict.fromkeys(order) if i in have]
    ordered += [i for i, _ in default_layout(p) if i not in ordered]
    return {"order": ordered, "hidden": [i for i in dict.fromkeys(hidden) if i in have]}
