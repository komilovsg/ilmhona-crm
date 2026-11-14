"""Numbers of the role dashboards (superadmin and manager): the month in one sentence, the
cohort timeline, the attention alerts, course demand, income per branch, the manager's queues.

Definitions:
- Month hero: collected / expected of this month (`goals.collection_month`, the goal's own
  figure); deltas compare the month so far with the same days of the previous month.
- Timeline: cohorts «набор» or «активный» that overlap the three calendar months starting with
  this one; seats = enrolled (not expelled) / planned capacity, over capacity is shown as such.
- Alerts: an enrollment-month is overpaid when pending + confirmed payments for it exceed the
  cohort's price; «без отметок» = held lessons with someone unmarked, started 5+ days ago
  (the «не заполнено» metric); pending = payments waiting for confirmation; a cohort in
  recruitment that starts within 14 days is under-filled below 50 % of its seats.
- Demand: leads created in the last 30 days (today included) against the 30 before; leads
  without a course are counted apart.
- Branch income: confirmed payments by payment month per branch, last 6 months.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.metrics import cohort_enrolled, fill_percent, over_capacity_of, unfilled_lessons
from app.metrics.goals import _new_enrollments, collection_month, pct
from app.metrics.money import (
    CONFIRMED,
    PENDING,
    TZ,
    ZERO,
    debt_summary,
    finance,
    first_of_month,
    income_total,
    money,
    month_index,
    payment_joined,
    payment_totals,
    today,
)
from app.metrics.reports import Scope, _in_period, _ym, month_end, month_list
from app.metrics.sales import CALLBACK, lead_period
from app.models import Branch, Cohort, Course, Enrollment, Lead, Payment, Student

TIMELINE_MONTHS = 3
TIMELINE_CAP = 30
UNMARKED_DAYS = 5
SOON_DAYS = 14
SOON_FILL_BELOW = 50
DEMAND_DAYS = 30
RECRUITING, ACTIVE = "набор", "активный"


def change_pct(current: Decimal | int, previous: Decimal | int) -> float | None:
    """% change against the previous value; None when there is nothing to compare with."""
    return None if not previous else pct(current - previous, previous)


def _add_months(d: date, n: int) -> date:
    index = month_index(d) + n
    return date(index // 12, index % 12 + 1, 1)


def _students_created(where: list[ColumnElement[bool]], since: date, until: date) -> Any:
    start = datetime.combine(since, datetime.min.time(), tzinfo=TZ)
    end = datetime.combine(until + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    return (
        select(func.count())
        .select_from(Student)
        .where(*where, Student.created_at >= start, Student.created_at < end)
    )


# ---- the month in one sentence ---------------------------------------------------------------


async def month_hero(db: AsyncSession, scope: Scope, on: date | None = None) -> dict[str, Any]:
    on = on or today()
    first = first_of_month(on)
    prev_first = _add_months(first, -1)
    prev_to = min(prev_first + timedelta(days=on.day - 1), month_end(prev_first))
    collected, expected = await collection_month(db, scope.cohort, on)
    debtors, debt = await debt_summary(db, scope.cohort, on)
    income = await income_total(db, scope.cohort, *_in_period(Payment.paid_at, first, on))
    income_prev = await income_total(
        db, scope.cohort, *_in_period(Payment.paid_at, prev_first, prev_to)
    )
    fin = await finance(db, scope.cohort, scope.campaign, first, month_end(first))
    students = (await db.execute(_students_created(scope.student, first, on))).scalar_one()
    students_prev = (
        await db.execute(_students_created(scope.student, prev_first, prev_to))
    ).scalar_one()
    return {
        "month": first,
        "collected": collected,
        "expected": expected,
        "collection_pct": pct(collected, expected) if expected else 0.0,
        "debt": debt,
        "debtors": debtors,
        "profit": fin["profit"],
        "income": income,
        "income_prev": income_prev,
        "income_change_pct": change_pct(income, income_prev),
        "new_students": students,
        "new_students_prev": students_prev,
        "new_students_change": students - students_prev,
    }


# ---- cohort timeline -------------------------------------------------------------------------


async def cohort_lanes(db: AsyncSession, scope: Scope, on: date | None = None) -> dict[str, Any]:
    on = on or today()
    win_start = first_of_month(on)
    win_end = month_end(_add_months(win_start, TIMELINE_MONTHS - 1))
    rows = (
        await db.execute(
            select(Cohort, Course.name, Branch.name)
            .join(Course, Course.id == Cohort.course_id)
            .join(Branch, Branch.id == Cohort.branch_id)
            .where(
                *scope.cohort,
                Cohort.status.in_((RECRUITING, ACTIVE)),
                Cohort.start_date <= win_end,
                Cohort.end_date >= win_start,
            )
            .order_by(Cohort.start_date, Cohort.code)
            .limit(TIMELINE_CAP)
        )
    ).all()
    enrolled = await cohort_enrolled(db, [c.id for c, _, _ in rows])
    items = [
        {
            "id": c.id,
            "code": c.code,
            "course_name": course,
            "branch_name": branch,
            "status": c.status,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "enrolled": enrolled[c.id],
            "capacity": c.capacity,
            "fill_pct": fill_percent(enrolled[c.id], c.capacity),
            "over_capacity": over_capacity_of(enrolled[c.id], c.capacity),
        }
        for c, course, branch in rows
    ]
    return {"window_start": win_start, "window_end": win_end, "today": on, "items": items}


async def open_cohorts(
    db: AsyncSession, scope: Scope, on: date | None = None, limit: int = 6
) -> list[dict[str, Any]]:
    """Cohorts in recruitment that have not started yet (or start today), soonest first, with the
    seats still free (never negative; over capacity is reported separately)."""
    on = on or today()
    rows = (
        await db.execute(
            select(Cohort, Course.name)
            .join(Course, Course.id == Cohort.course_id)
            .where(*scope.cohort, Cohort.status == RECRUITING, Cohort.start_date >= on)
            .order_by(Cohort.start_date, Cohort.code)
            .limit(limit)
        )
    ).all()
    enrolled = await cohort_enrolled(db, [c.id for c, _ in rows])
    return [
        {
            "id": c.id,
            "code": c.code,
            "course_name": course,
            "start_date": c.start_date,
            "enrolled": enrolled[c.id],
            "capacity": c.capacity,
            "free": max(c.capacity - enrolled[c.id], 0),
            "fill_pct": fill_percent(enrolled[c.id], c.capacity),
            "over_capacity": over_capacity_of(enrolled[c.id], c.capacity),
        }
        for c, course in rows
    ]


# ---- alerts ----------------------------------------------------------------------------------


async def overpaid_months(
    db: AsyncSession, cohort_where: list[ColumnElement[bool]]
) -> list[dict[str, Any]]:
    """Enrollment-months where pending + confirmed payments exceed the price, biggest first."""
    entered = func.sum(Payment.amount)
    rows = (
        await db.execute(
            select(
                Cohort.id,
                Cohort.code,
                Enrollment.id,
                Student.full_name,
                Payment.month_no,
                (entered - Cohort.price_month).label("over"),
            )
            .select_from(Payment)
            .join(Enrollment, Enrollment.id == Payment.enrollment_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .join(Student, Student.id == Enrollment.student_id)
            .where(*cohort_where, Payment.status.in_((PENDING, CONFIRMED)), Cohort.price_month > 0)
            .group_by(
                Cohort.id,
                Cohort.code,
                Cohort.price_month,
                Enrollment.id,
                Student.full_name,
                Payment.month_no,
            )
            .having(entered > Cohort.price_month)
        )
    ).all()
    out: list[dict[str, Any]] = [
        {
            "cohort_id": cid,
            "cohort_code": code,
            "enrollment_id": eid,
            "student_name": name,
            "month_no": month_no,
            "overpaid": money(over),
        }
        for cid, code, eid, name, month_no, over in rows
    ]
    out.sort(key=lambda r: (r["overpaid"] * -1, str(r["cohort_code"]), int(r["month_no"])))
    return out


async def unmarked_cohorts(
    db: AsyncSession,
    cohort_where: list[ColumnElement[bool]],
    min_days: int = UNMARKED_DAYS,
) -> list[dict[str, Any]]:
    """Cohorts that have a held lesson with somebody unmarked for `min_days`+ days."""
    cutoff = clock.now() - timedelta(days=min_days)
    seen: dict[uuid.UUID, str] = {}
    for lesson, cohort, *_ in await unfilled_lessons(db, cohort_where):
        if lesson.starts_at <= cutoff:
            seen[cohort.id] = cohort.code
    return [{"cohort_id": i, "cohort_code": c} for i, c in sorted(seen.items(), key=lambda t: t[1])]


async def pending_payments(
    db: AsyncSession, cohort_where: list[ColumnElement[bool]], on: date | None = None
) -> dict[str, Any]:
    """Payments waiting for confirmation: how many, the sum and the age in days of the oldest
    (by the day it was entered, Dushanbe time)."""
    on = on or today()
    totals = await payment_totals(db, [*cohort_where, Payment.status == PENDING])
    oldest = (
        await db.execute(
            payment_joined(select(func.min(func.timezone(TZ.key, Payment.created_at)))).where(
                *cohort_where, Payment.status == PENDING
            )
        )
    ).scalar_one()
    return {
        "count": totals["pending_count"],
        "sum": totals["pending"],
        "oldest_days": max((on - oldest.date()).days, 0) if oldest else None,
    }


async def starting_soon_underfilled(
    db: AsyncSession,
    cohort_where: list[ColumnElement[bool]],
    on: date | None = None,
    days: int = SOON_DAYS,
    below: int = SOON_FILL_BELOW,
) -> list[dict[str, Any]]:
    on = on or today()
    rows = (
        (
            await db.execute(
                select(Cohort)
                .where(
                    *cohort_where,
                    Cohort.status == RECRUITING,
                    Cohort.start_date >= on,
                    Cohort.start_date <= on + timedelta(days=days),
                    Cohort.capacity > 0,
                )
                .order_by(Cohort.start_date, Cohort.code)
            )
        )
        .scalars()
        .all()
    )
    enrolled = await cohort_enrolled(db, [c.id for c in rows])
    return [
        {
            "cohort_id": c.id,
            "cohort_code": c.code,
            "starts_in_days": (c.start_date - on).days,
            "enrolled": enrolled[c.id],
            "capacity": c.capacity,
        }
        for c in rows
        if enrolled[c.id] * 100 < below * c.capacity
    ]


# ---- demand and branches ---------------------------------------------------------------------


async def lead_demand(
    db: AsyncSession, scope: Scope, on: date | None = None, limit: int = 6
) -> dict[str, Any]:
    """Leads per course: the last 30 days against the 30 before, and leads with no course."""
    on = on or today()
    cur_from = on - timedelta(days=DEMAND_DAYS - 1)
    prev_from = cur_from - timedelta(days=DEMAND_DAYS)
    prev_to = cur_from - timedelta(days=1)

    async def counts(since: date, until: date) -> dict[uuid.UUID | None, int]:
        rows = await db.execute(
            select(Lead.course_id, func.count())
            .where(*scope.leads(since, until))
            .group_by(Lead.course_id)
        )
        return {k: n for k, n in rows.all()}

    cur, prev = await counts(cur_from, on), await counts(prev_from, prev_to)
    names = dict((await db.execute(select(Course.id, Course.name))).all())
    items: list[dict[str, Any]] = [
        {
            "course_id": cid,
            "course_name": names[cid],
            "leads": cur.get(cid, 0),
            "previous": prev.get(cid, 0),
            "change_pct": change_pct(cur.get(cid, 0), prev.get(cid, 0)),
        }
        for cid in {*cur, *prev}
        if cid is not None
    ]
    items.sort(key=lambda r: (r["leads"] * -1, r["previous"] * -1, str(r["course_name"])))
    return {
        "since": cur_from,
        "until": on,
        "items": items[:limit],
        "no_course": cur.get(None, 0),
        "total": sum(cur.values()),
    }


async def income_by_branch_month(
    db: AsyncSession, scope: Scope, on: date | None = None
) -> dict[str, Any]:
    months = month_list(on, 6)
    since, until = months[0], month_end(months[-1])
    rows = (
        await db.execute(
            select(Cohort.branch_id, _ym(Payment.paid_at), func.sum(Payment.amount))
            .select_from(Payment)
            .join(Enrollment, Enrollment.id == Payment.enrollment_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(
                Payment.status == CONFIRMED,
                *scope.cohort,
                *_in_period(Payment.paid_at, since, until),
            )
            .group_by(Cohort.branch_id, _ym(Payment.paid_at))
        )
    ).all()
    got = {(b, ym): money(total) for b, ym, total in rows}
    only = scope.branch_id or scope.p.branch_id
    branches = (
        await db.execute(
            select(Branch.id, Branch.name)
            .where(*([Branch.id == only] if only else []))
            .order_by(Branch.name)
        )
    ).all()
    return {
        "months": months,
        "series": [
            {
                "branch_id": bid,
                "name": name,
                "values": [got.get((bid, f"{m:%Y-%m}"), ZERO) for m in months],
            }
            for bid, name in branches
        ],
    }


# ---- manager's day ---------------------------------------------------------------------------


def _day_start(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=TZ)


async def callbacks_overdue(db: AsyncSession, lead_where: list[Any], on: date | None = None) -> int:
    """Callbacks due before today began (a part of «перезвонить сегодня»)."""
    on = on or today()
    return (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                *lead_where,
                Lead.call_status == CALLBACK,
                Lead.next_contact_at < _day_start(on),
            )
        )
    ).scalar_one()


async def leads_created(db: AsyncSession, lead_where: list[Any], since: date, until: date) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Lead).where(*lead_where, *lead_period(since, until))
        )
    ).scalar_one()


async def week_summary(db: AsyncSession, scope: Scope, on: date | None = None) -> dict[str, Any]:
    """The last 7 days (today included) against the 7 before."""
    on = on or today()
    since = on - timedelta(days=6)
    prev_since, prev_to = since - timedelta(days=7), since - timedelta(days=1)
    leads = await leads_created(db, scope.leads(), since, on)
    leads_prev = await leads_created(db, scope.leads(), prev_since, prev_to)
    enrolled = await _new_enrollments(db, scope.cohort, since, on)
    enrolled_prev = await _new_enrollments(db, scope.cohort, prev_since, prev_to)
    paid = await payment_totals(
        db, [*scope.cohort, Payment.status == CONFIRMED, *_in_period(Payment.paid_at, since, on)]
    )
    debtors, debt = await debt_summary(db, scope.cohort, on)
    return {
        "since": since,
        "until": on,
        "leads": leads,
        "leads_change": leads - leads_prev,
        "enrolled": enrolled,
        "enrolled_change": enrolled - enrolled_prev,
        "payments_count": paid["confirmed_count"],
        "payments_sum": paid["confirmed"],
        "debt": debt,
        "debtors": debtors,
    }
