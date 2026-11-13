"""Grading schemes and totals (SPEC «Оценки»): the one calculation behind every total and pass.

- A scheme = ordered categories {key, name, weight, kind} whose weights sum to exactly 100, one
  `attendance` category (points computed) and `manual` ones (the teacher enters 0..weight), plus
  the pass score and the targets (retention, attendance, pass rate, %).
- The academy standard (`grading_scheme.cohort_id` NULL) applies to every cohort without a scheme
  of its own; a cohort's own scheme replaces it whole.
- Attendance points = round(weight × present / held), halves up; no held lesson yet = 0.
- Manual points = the entered score, capped at the category weight (a weight lowered after the
  scores were entered never lets a category give more than it weighs); empty = 0.
- Total = Σ category points. Passed = total ≥ the scheme's pass score.
- Projected = the total scaled up from the categories that already have something to count:
  attendance once a lesson was held, a manual category once a score is entered.
  projected = round(100 × total ÷ Σ weights of those categories); none of them yet = None.
- Scores whose category is not in the scheme (removed, or never part of it) are archived: kept,
  not counted, listed by `archived_scores`.
"""

import uuid
from decimal import Decimal
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GradingCategory, GradingScheme

ATTENDANCE = "attendance"
MANUAL = "manual"
ATTENDANCE_KEY = "attendance"
TOTAL = 100
MAX_CATEGORIES = 12
STANDARD = "standard"
OWN = "cohort"


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    weight: int
    kind: str


@dataclass(frozen=True)
class Scheme:
    id: uuid.UUID
    cohort_id: uuid.UUID | None
    version: int
    categories: tuple[Category, ...]
    pass_score: int
    target_retention: int
    target_attendance: int
    target_pass_rate: int

    @property
    def source(self) -> str:
        return STANDARD if self.cohort_id is None else OWN

    @property
    def manual(self) -> tuple[Category, ...]:
        return tuple(c for c in self.categories if c.kind == MANUAL)

    @property
    def attendance(self) -> Category:
        return next(c for c in self.categories if c.kind == ATTENDANCE)

    def weights(self) -> dict[str, int]:
        return {c.name: c.weight for c in self.categories}


def scaled_points(weight: int, present: int, held: int) -> int:
    """round(weight × present / held), halves up; no held lessons yet = 0."""
    if held <= 0:
        return 0
    return (2 * weight * present + held) // (2 * held)


def _ratio(part: int, whole: int) -> int:
    """round(100 × part / whole), halves up."""
    return (200 * part + whole) // (2 * whole)


def result(scheme: Scheme, present: int, held: int, scores: dict[str, int]) -> dict[str, Any]:
    """Points per category, total, projected and passed of one enrollment."""
    points: dict[str, int] = {}
    counted = 0
    for c in scheme.categories:
        if c.kind == ATTENDANCE:
            points[c.key] = scaled_points(c.weight, present, held)
            counted += c.weight if held > 0 else 0
        else:
            raw = scores.get(c.key)
            points[c.key] = min(raw, c.weight) if raw is not None else 0
            counted += c.weight if raw is not None else 0
    total = sum(points.values())
    return {
        "points": points,
        "attendance_score": points[scheme.attendance.key],
        "total": total,
        "projected": _ratio(total, counted) if counted else None,
        "passed": passes(scheme, total),
    }


def passes(scheme: Scheme, total: int | Decimal) -> bool:
    return total >= scheme.pass_score


def _build(row: GradingScheme, categories: Iterable[GradingCategory]) -> Scheme:
    return Scheme(
        id=row.id,
        cohort_id=row.cohort_id,
        version=row.version,
        categories=tuple(
            Category(c.key, c.name, c.weight, c.kind)
            for c in sorted(categories, key=lambda c: c.position)
        ),
        pass_score=row.pass_score,
        target_retention=row.target_retention,
        target_attendance=row.target_attendance,
        target_pass_rate=row.target_pass_rate,
    )


async def _load(db: AsyncSession, cohort_ids: Sequence[uuid.UUID]) -> list[Scheme]:
    """The standard and the own schemes of `cohort_ids`: one query."""
    where: ColumnElement[bool] = GradingScheme.cohort_id.is_(None)
    if cohort_ids:
        where = or_(where, GradingScheme.cohort_id.in_(list(cohort_ids)))
    rows = (
        await db.execute(
            select(GradingScheme, GradingCategory)
            .join(GradingCategory, GradingCategory.scheme_id == GradingScheme.id)
            .where(where)
        )
    ).all()
    found: dict[uuid.UUID, tuple[GradingScheme, list[GradingCategory]]] = {}
    for scheme, category in rows:
        found.setdefault(scheme.id, (scheme, []))[1].append(category)
    return [_build(s, cats) for s, cats in found.values()]


async def schemes_for(db: AsyncSession, cohort_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Scheme]:
    """The effective scheme of each cohort: its own, else the academy standard."""
    ids = list(set(cohort_ids))
    loaded = await _load(db, ids)
    standard = next(s for s in loaded if s.cohort_id is None)
    own = {s.cohort_id: s for s in loaded if s.cohort_id is not None}
    return {i: own.get(i, standard) for i in ids}


async def standard_scheme(db: AsyncSession) -> Scheme:
    return next(s for s in await _load(db, []) if s.cohort_id is None)


async def scheme_of(db: AsyncSession, cohort_id: uuid.UUID) -> Scheme:
    return (await schemes_for(db, [cohort_id]))[cohort_id]


async def own_scheme(db: AsyncSession, cohort_id: uuid.UUID) -> Scheme | None:
    found = [s for s in await _load(db, [cohort_id]) if s.cohort_id == cohort_id]
    return found[0] if found else None
