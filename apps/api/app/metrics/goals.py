"""Goal numbers (owner goals of the academy): the current value of a metric, progress, pace.

Metrics (all branch-scoped when the goal has a branch; the period is start_date..deadline, both
days included):
- graduates_total: graduates as the dashboard counts them (`graduate_count`), by the end date of
  their cohort inside the period.
- active_students: students with an active enrollment right now (`student_counts`), no period.
- collection_rate_month: % of this month's expected payments that are confirmed. Expected = the
  price of the current month for every enrollment that owes it (`owed_month_numbers`, not expelled,
  cohort not cancelled); collected = the confirmed part of that month, capped at the price.
- income: confirmed payments by payment date inside the period (`income_total`).
- new_enrollments: enrollments made inside the period (Dushanbe day), cohorts not cancelled.
- courses_launched: courses whose FIRST cohort (not cancelled) starts inside the period.

Pace: cumulative metrics are expected to grow linearly from start_date to deadline (0 % on the
start day, 100 % on the deadline); a rate metric is expected to sit at its target all the time.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal
from app.metrics import student_counts
from app.metrics.money import (
    CANCELLED,
    TZ,
    ZERO,
    debtor_where,
    enrollment_money_rows,
    income_total,
    month_index,
    today,
)
from app.metrics.reports import Scope, graduate_count, graduate_where
from app.models import Cohort, Enrollment, Payment

METRICS: dict[str, str] = {
    "graduates_total": "Выпускники: сколько студентов окончили поток за период",
    "active_students": "Активные студенты: сколько учатся сейчас",
    "collection_rate_month": "Сбор оплат за месяц: % подтверждённых оплат от ожидаемых",
    "income": "Доход: подтверждённые оплаты за период, TJS",
    "new_enrollments": "Новые зачисления: сколько студентов зачислено за период",
    "courses_launched": "Запуски курсов: курсы, у которых первый поток стартовал в период",
}
RATE_METRICS = frozenset({"collection_rate_month"})

REACHED, ON_TRACK, BEHIND, OVERDUE = "достигнута", "по графику", "отстаём", "срок прошёл"


async def _collection_rate(db: AsyncSession, cohort_where: list[ColumnElement[bool]]) -> float:
    on = today()
    rows = (
        await db.execute(
            select(
                Enrollment.id,
                Enrollment.enrolled_at,
                Enrollment.status,
                Cohort.price_month,
                Cohort.start_date,
                Cohort.end_date,
            )
            .select_from(Enrollment)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(*cohort_where, *debtor_where())
        )
    ).all()
    by = await enrollment_money_rows(db, [tuple(r) for r in rows], on)  # type: ignore[misc]
    expected = collected = ZERO
    for eid, _, _, price, start, _ in rows:
        month_no = month_index(on) - month_index(start) + 1
        info = next((m for m in by[eid]["month_states"] if m["month_no"] == month_no), None)
        if info is None or not info["started"]:
            continue
        expected += price
        collected += min(info["confirmed"], price)
    return round(float(collected * 100 / expected), 1) if expected else 0.0


async def _new_enrollments(
    db: AsyncSession, cohort_where: list[ColumnElement[bool]], since: date, until: date
) -> int:
    day = cast(func.timezone(TZ.key, Enrollment.enrolled_at), Date)
    n: int = (
        await db.execute(
            select(func.count())
            .select_from(Enrollment)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(*cohort_where, Cohort.status != CANCELLED, day >= since, day <= until)
        )
    ).scalar_one()
    return n


async def _courses_launched(
    db: AsyncSession, cohort_where: list[ColumnElement[bool]], since: date, until: date
) -> int:
    first = (
        select(func.min(Cohort.start_date).label("first"))
        .where(*cohort_where, Cohort.status != CANCELLED)
        .group_by(Cohort.course_id)
        .subquery()
    )
    n: int = (
        await db.execute(
            select(func.count()).select_from(first).where(first.c.first.between(since, until))
        )
    ).scalar_one()
    return n


async def current_value(
    db: AsyncSession,
    p: Principal,
    metric: str,
    branch_id: uuid.UUID | None,
    since: date,
    until: date,
) -> float:
    scope = Scope.of(p, branch_id)
    if metric == "graduates_total":
        return float(await graduate_count(db, graduate_where(scope, since, until)))
    if metric == "active_students":
        return float((await student_counts(db, scope.student))["активный"])
    if metric == "collection_rate_month":
        return await _collection_rate(db, scope.cohort)
    if metric == "income":
        paid = [Payment.paid_at >= since, Payment.paid_at <= until]
        return float(await income_total(db, scope.cohort, *paid))
    if metric == "new_enrollments":
        return float(await _new_enrollments(db, scope.cohort, since, until))
    if metric == "courses_launched":
        return float(await _courses_launched(db, scope.cohort, since, until))
    raise ValueError(f"unknown goal metric {metric!r}")


def pace(
    metric: str, current: float, target: Decimal | float, start: date, deadline: date, on: date
) -> dict[str, Any]:
    """progress %, expected % and the status of a goal on day `on`."""
    goal = float(target)
    progress = min(round(current * 100 / goal, 1), 100.0)
    if metric in RATE_METRICS:
        expected = 100.0
    else:
        elapsed = (min(max(on, start), deadline) - start).days
        expected = round(elapsed * 100 / (deadline - start).days, 1)
    on_pace = progress >= expected
    if current >= goal:
        status = REACHED
    elif on > deadline:
        status = OVERDUE
    else:
        status = ON_TRACK if on_pace else BEHIND
    return {
        "progress_pct": progress,
        "expected_pct": expected,
        "on_pace": on_pace,
        "status": status,
    }
