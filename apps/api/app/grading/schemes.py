"""Editing grading schemes: the rules a new scheme must meet, writing it, what it archives.

One validation (`problems`) serves the API and the Excel import, so both refuse the same things
with the same Russian sentences. Category keys stay stable across edits: a category sent with a
known key, or with the name of a known category, keeps that key (so its scores stay attached); a
new one gets a fresh key. The attendance category's key is always `attendance`.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import DomainError
from app.grading.errors import GRADING_SCHEME_INVALID, GRADING_SCORES_ARCHIVED
from app.metrics import grading as g
from app.models import Enrollment, GradeScore, GradingCategory, GradingKey, GradingScheme

NAME_MAX = 60
TARGETS = ("target_retention", "target_attendance", "target_pass_rate")
FIELDS = ("pass_score", *TARGETS)

Percent = Annotated[int, Field(ge=0, le=100)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryIn(Strict):
    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")] | None = None
    name: Name
    weight: Percent
    kind: Literal["attendance", "manual"]


class SchemeIn(Strict):
    """Only the fields sent change; `categories` is the whole ordered list."""

    categories: (
        Annotated[list[CategoryIn], Field(min_length=1, max_length=g.MAX_CATEGORIES)] | None
    ) = None
    pass_score: Percent | None = None
    target_retention: Percent | None = None
    target_attendance: Percent | None = None
    target_pass_rate: Percent | None = None
    # removing a category that has entered scores: the scores are kept (archived), but the user
    # confirms it first
    confirm_archive: bool = False


@dataclass(frozen=True)
class Draft:
    categories: tuple[g.Category, ...]
    pass_score: int
    target_retention: int
    target_attendance: int
    target_pass_rate: int


def problems(categories: Sequence[tuple[str, int, str]]) -> list[str]:
    """What is wrong with (name, weight, kind) categories, in Russian; empty = fine."""
    out: list[str] = []
    if not categories:
        return ["Нет ни одной категории"]
    if len(categories) > g.MAX_CATEGORIES:
        out.append(f"Категорий {len(categories)}, можно не больше {g.MAX_CATEGORIES}")
    seen: set[str] = set()
    for name, weight, kind in categories:
        low = name.strip().lower()
        if low in seen:
            out.append(f"Категория «{name}» повторяется")
        seen.add(low)
        if kind == g.MANUAL and weight < 1:
            out.append(f"«{name}»: у категории, которую заполняет преподаватель, баллов от 1")
    att = sum(1 for _, _, kind in categories if kind == g.ATTENDANCE)
    if att != 1:
        out.append(f"Категория «посещаемость» (авто) должна быть ровно одна, сейчас {att}")
    total = sum(w for _, w, _ in categories)
    if total != g.TOTAL:
        out.append(f"Сумма баллов {total} из {g.TOTAL}: должно быть ровно {g.TOTAL}")
    return out


def _new_key() -> str:
    return f"c{uuid.uuid4().hex[:10]}"


def resolve(
    sent: Sequence[CategoryIn], known: Sequence[g.Category], names: dict[str, str]
) -> tuple[g.Category, ...]:
    """Keys for the sent categories: a key of `known` stays; a name of `known` (or of an
    archived key, `names`) takes that key; anything else gets a new key."""
    by_key = {c.key: c for c in known if c.kind == g.MANUAL}
    by_name = {n.strip().lower(): k for k, n in names.items() if k != g.ATTENDANCE_KEY}
    by_name.update({c.name.strip().lower(): c.key for c in known if c.kind == g.MANUAL})
    out: list[g.Category] = []
    used: set[str] = set()
    for c in sent:
        if c.kind == g.ATTENDANCE:
            key = g.ATTENDANCE_KEY
        elif c.key in by_key and c.key not in used:
            key = c.key
        else:
            key = by_name.get(c.name.strip().lower()) or _new_key()
            if key in used:
                key = _new_key()
        used.add(key)
        out.append(g.Category(key, c.name.strip(), c.weight, c.kind))
    return tuple(out)


async def key_names(db: AsyncSession) -> dict[str, str]:
    return {k: n for k, n in (await db.execute(select(GradingKey.key, GradingKey.name))).all()}


def draft_of(base: g.Scheme, body: SchemeIn, names: dict[str, str]) -> Draft:
    """`base` with the sent fields applied; 422 with the problems when it breaks a rule."""
    categories = (
        resolve(body.categories, base.categories, names)
        if body.categories is not None
        else base.categories
    )
    found = problems([(c.name, c.weight, c.kind) for c in categories])
    if found:
        raise DomainError(GRADING_SCHEME_INVALID, problems=found)
    values = {f: getattr(body, f) for f in FIELDS}
    return Draft(
        categories=categories,
        **{f: getattr(base, f) if values[f] is None else values[f] for f in FIELDS},
    )


def _weights(categories: Sequence[g.Category]) -> str:
    return ", ".join(f"{c.name} {c.weight}" for c in categories)


def change_diff(before: g.Scheme | Draft, after: g.Scheme | Draft) -> dict[str, Any]:
    """The audit diff: the categories with their points before → after, then the numbers."""
    diff: dict[str, Any] = {}
    if before.categories != after.categories:
        diff["categories"] = [_weights(before.categories), _weights(after.categories)]
    for f in FIELDS:
        if getattr(before, f) != getattr(after, f):
            diff[f] = [getattr(before, f), getattr(after, f)]
    return diff


async def archived_by(
    db: AsyncSession,
    removed: set[str],
    *,
    cohort_id: uuid.UUID | None,
) -> dict[str, int]:
    """{key: entered scores} of `removed` keys in one cohort, or (cohort None) in every cohort
    that follows the standard."""
    if not removed:
        return {}
    query = (
        select(GradeScore.category_key, func.count())
        .join(Enrollment, Enrollment.id == GradeScore.enrollment_id)
        .where(GradeScore.category_key.in_(removed))
        .group_by(GradeScore.category_key)
    )
    if cohort_id is not None:
        query = query.where(Enrollment.cohort_id == cohort_id)
    else:
        query = query.where(
            Enrollment.cohort_id.not_in(
                select(GradingScheme.cohort_id).where(GradingScheme.cohort_id.is_not(None))
            )
        )
    return {k: n for k, n in (await db.execute(query)).all()}


async def check_archive(
    db: AsyncSession,
    before: Sequence[g.Category],
    after: Sequence[g.Category],
    *,
    cohort_id: uuid.UUID | None,
    confirmed: bool,
) -> list[dict[str, Any]]:
    """The removed categories that have scores; 409 unless the user confirmed. The scores stay
    in `grade_score` either way."""
    removed = {c.key for c in before if c.kind == g.MANUAL} - {c.key for c in after}
    counts = await archived_by(db, removed, cohort_id=cohort_id)
    names = {c.key: c.name for c in before}
    lost = [
        {"key": c.key, "name": names[c.key], "scores": counts[c.key]}
        for c in before
        if counts.get(c.key)
    ]
    if lost and not confirmed:
        raise DomainError(
            GRADING_SCORES_ARCHIVED,
            categories=[{"name": x["name"], "scores": x["scores"]} for x in lost],
        )
    return lost


async def write(
    db: AsyncSession, row: GradingScheme, draft: Draft, actor_id: uuid.UUID | None
) -> None:
    """Replace the categories and numbers of `row`; the version moves on (updated_at changes)."""
    await db.execute(delete(GradingCategory).where(GradingCategory.scheme_id == row.id))
    for position, c in enumerate(draft.categories):
        db.add(
            GradingCategory(
                scheme_id=row.id,
                key=c.key,
                name=c.name,
                weight=c.weight,
                kind=c.kind,
                position=position,
            )
        )
    for f in FIELDS:
        setattr(row, f, getattr(draft, f))
    row.updated_at = clock.now()
    row.updated_by = actor_id
    await remember_names(db, draft.categories)
    await db.flush()
    # the sum-100 / one-attendance trigger runs now, not at commit
    await db.execute(text("SET CONSTRAINTS grading_category_check, grading_scheme_check IMMEDIATE"))


async def remember_names(db: AsyncSession, categories: Sequence[g.Category]) -> None:
    rows = [{"key": c.key, "name": c.name} for c in categories]
    stmt = pg_insert(GradingKey).values(rows)
    await db.execute(
        stmt.on_conflict_do_update(index_elements=["key"], set_={"name": stmt.excluded.name})
    )


def scheme_out(scheme: g.Scheme | Draft) -> dict[str, Any]:
    return {
        "categories": [
            {"key": c.key, "name": c.name, "weight": c.weight, "kind": c.kind}
            for c in scheme.categories
        ],
        **{f: getattr(scheme, f) for f in FIELDS},
    }
