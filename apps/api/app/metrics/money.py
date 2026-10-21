"""Money numbers (SPEC «Метрики»): the one place that computes them.

- A cohort runs over calendar months: `cohort_months` = months from the start month to the end
  month, inclusive. Payment `month_no` is 1..cohort_months; the salary period is the first day of
  the month.
- Only a confirmed payment counts. Per enrollment: paid = confirmed sum, paid months = distinct
  `month_no` with a confirmed payment, expected = price_month × months started since enrollment
  (from the later of the enrollment month and the cohort start month, to the earlier of this month
  and the cohort's last month), debt = max(expected − paid, 0). An expelled student owes nothing
  more: debt 0.
- «Оплатили» (#5) = enrollments with ≥ 1 confirmed payment among the enrolled (not expelled), so
  it can never exceed «записались».
- Income = confirmed payments; payroll (расходы ЗП, #9) = the sum of instructor payouts, never the
  schedule; ads = budgets of the campaigns that started in the period (stage 3); profit = income −
  ads − payroll. With a period: income by payment date, payroll by payout date, ads by start date.
- Salary schedule: every month a cohort (not cancelled, with an instructor) runs × the cohort's
  rate. Paid = payouts actually made; due = max(rate − paid, 0).
- Instructor card (#17): cohorts, students, income from own cohorts, payouts. No «efficiency %».
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import (
    AppUser,
    Campaign,
    Cohort,
    Course,
    Enrollment,
    InstructorPayout,
    Payment,
    Student,
)

TZ = ZoneInfo("Asia/Dushanbe")
CONFIRMED = "подтверждено"
PENDING = "ожидает"
EXPELLED = "отчислен"
CANCELLED = "отменён"
ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    """A sum from the database as money: two decimals, also for an empty sum (0 -> 0.00)."""
    return Decimal(value).quantize(CENT)


def today() -> date:
    return clock.today()


def month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def cohort_months(start: date, end: date) -> int:
    return month_index(end) - month_index(start) + 1


def cohort_periods(start: date, end: date) -> list[date]:
    """First day of every month the cohort runs."""
    first = month_index(start)
    return [
        date((first + i) // 12, (first + i) % 12 + 1, 1) for i in range(cohort_months(start, end))
    ]


def expected_months(enrolled_on: date, start: date, end: date, on: date) -> int:
    first = max(month_index(enrolled_on), month_index(start))
    last = min(month_index(on), month_index(end))
    return max(0, last - first + 1)


def expected_amount(price: Decimal, enrolled_at: datetime, cohort: Cohort, on: date) -> Decimal:
    local = enrolled_at.astimezone(TZ).date()
    return price * expected_months(local, cohort.start_date, cohort.end_date, on)


def debt_of(expected: Decimal, paid: Decimal, status: str) -> Decimal:
    return ZERO if status == EXPELLED else max(expected - paid, ZERO)


# ---- payments ----------------------------------------------------------------------------


def payment_joined(query: Any) -> Any:
    """Payment -> enrollment -> cohort -> student: the joins every payment list and total shares."""
    return (
        query.select_from(Payment)
        .join(Enrollment, Enrollment.id == Payment.enrollment_id)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .join(Student, Student.id == Enrollment.student_id)
    )


async def payment_totals(db: AsyncSession, where: Sequence[ColumnElement[bool]]) -> dict[str, Any]:
    """Confirmed / pending sums and counts of the payments matching `where`."""
    rows = await db.execute(
        payment_joined(
            select(Payment.status, func.count(), func.coalesce(func.sum(Payment.amount), 0))
        )
        .where(*where)
        .group_by(Payment.status)
    )
    by = {s: (n, money(total)) for s, n, total in rows.all()}
    confirmed, pending = by.get(CONFIRMED, (0, ZERO)), by.get(PENDING, (0, ZERO))
    return {
        "confirmed": confirmed[1],
        "pending": pending[1],
        "confirmed_count": confirmed[0],
        "pending_count": pending[0],
        "count": confirmed[0] + pending[0],
    }


async def enrollment_money(
    db: AsyncSession, rows: Sequence[tuple[Enrollment, Cohort]], on: date | None = None
) -> dict[uuid.UUID, dict[str, Any]]:
    """paid, paid months, expected and debt per enrollment (every given enrollment is present)."""
    on = on or today()
    ids = [e.id for e, _ in rows]
    paid: dict[uuid.UUID, tuple[Decimal, list[int]]] = {}
    if ids:
        result = await db.execute(
            select(
                Payment.enrollment_id,
                func.coalesce(func.sum(Payment.amount), 0),
                func.array_agg(func.distinct(Payment.month_no)),
            )
            .where(Payment.enrollment_id.in_(ids), Payment.status == CONFIRMED)
            .group_by(Payment.enrollment_id)
        )
        paid = {i: (money(total), sorted(months)) for i, total, months in result.all()}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for e, cohort in rows:
        total, months = paid.get(e.id, (ZERO, []))
        expected = expected_amount(cohort.price_month, e.enrolled_at, cohort, on)
        out[e.id] = {
            "paid": total,
            "paid_months": months,
            "expected": expected,
            "debt": debt_of(expected, total, e.status),
        }
    return out


async def cohort_payers(db: AsyncSession, cohort_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """«Оплатили» per cohort (#5): enrolled students with a confirmed payment."""
    if not cohort_ids:
        return {}
    rows = await db.execute(
        select(Enrollment.cohort_id, func.count(func.distinct(Enrollment.id)))
        .join(Payment, Payment.enrollment_id == Enrollment.id)
        .where(
            Enrollment.cohort_id.in_(cohort_ids),
            Enrollment.status != EXPELLED,
            Payment.status == CONFIRMED,
        )
        .group_by(Enrollment.cohort_id)
    )
    counts = dict(rows.all())
    return {c: counts.get(c, 0) for c in cohort_ids}


async def cohort_income(db: AsyncSession, cohort_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    if not cohort_ids:
        return {}
    rows = await db.execute(
        select(Enrollment.cohort_id, func.coalesce(func.sum(Payment.amount), 0))
        .join(Payment, Payment.enrollment_id == Enrollment.id)
        .where(Enrollment.cohort_id.in_(cohort_ids), Payment.status == CONFIRMED)
        .group_by(Enrollment.cohort_id)
    )
    got = {c: money(t) for c, t in rows.all()}
    return {c: got.get(c, ZERO) for c in cohort_ids}


# ---- profit ------------------------------------------------------------------------------


async def income_total(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    *extra: ColumnElement[bool],
) -> Decimal:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .join(Enrollment, Enrollment.id == Payment.enrollment_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(Payment.status == CONFIRMED, *cohort_where, *extra)
        )
    ).scalar_one()
    return money(total)


async def payroll_total(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    *extra: ColumnElement[bool],
) -> Decimal:
    """Расходы ЗП (#9): the payouts actually made."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(InstructorPayout.amount), 0))
            .join(Cohort, Cohort.id == InstructorPayout.cohort_id)
            .where(*cohort_where, *extra)
        )
    ).scalar_one()
    return money(total)


async def ads_total(
    db: AsyncSession,
    campaign_where: Sequence[ColumnElement[bool]],
    since: date | None = None,
    until: date | None = None,
) -> Decimal:
    """Реклама: the budgets of the campaigns that started in the period (all, with no period)."""
    where = list(campaign_where)
    if since:
        where.append(Campaign.start_date >= since)
    if until:
        where.append(Campaign.start_date <= until)
    total = (
        await db.execute(select(func.coalesce(func.sum(Campaign.budget), 0)).where(*where))
    ).scalar_one()
    return money(total)


async def finance(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    campaign_where: Sequence[ColumnElement[bool]] = (),
    since: date | None = None,
    until: date | None = None,
) -> dict[str, Any]:
    paid: list[ColumnElement[bool]] = []
    payouts: list[ColumnElement[bool]] = []
    if since:
        paid.append(Payment.paid_at >= since)
        payouts.append(InstructorPayout.paid_at >= since)
    if until:
        paid.append(Payment.paid_at <= until)
        payouts.append(InstructorPayout.paid_at <= until)
    income = await income_total(db, cohort_where, *paid)
    payroll = await payroll_total(db, cohort_where, *payouts)
    ads = await ads_total(db, campaign_where, since, until)
    return {"income": income, "payroll": payroll, "ads": ads, "profit": income - ads - payroll}


# ---- instructors and salaries -----------------------------------------------------------


async def instructor_stats(
    db: AsyncSession, instructor_ids: list[uuid.UUID], cohort_where: Sequence[ColumnElement[bool]]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Cohorts, students, income of own cohorts and payouts per instructor (#17: no efficiency)."""
    stats: dict[Any, dict[str, Any]] = {
        i: {"cohorts": 0, "active_cohorts": 0, "students": 0, "income": ZERO, "paid_out": ZERO}
        for i in instructor_ids
    }
    if not instructor_ids:
        return stats
    own = [Cohort.instructor_id.in_(instructor_ids), Cohort.status != CANCELLED, *cohort_where]
    r_cohorts = await db.execute(
        select(
            Cohort.instructor_id,
            func.count(),
            func.count().filter(Cohort.status == "активный"),
        )
        .where(*own)
        .group_by(Cohort.instructor_id)
    )
    for i, n, active in r_cohorts.all():
        stats[i]["cohorts"], stats[i]["active_cohorts"] = n, active
    r_students = await db.execute(
        select(Cohort.instructor_id, func.count(func.distinct(Enrollment.student_id)))
        .join(Enrollment, Enrollment.cohort_id == Cohort.id)
        .where(*own, Enrollment.status != EXPELLED)
        .group_by(Cohort.instructor_id)
    )
    for i, n in r_students.all():
        stats[i]["students"] = n
    r_income = await db.execute(
        select(Cohort.instructor_id, func.coalesce(func.sum(Payment.amount), 0))
        .join(Enrollment, Enrollment.cohort_id == Cohort.id)
        .join(Payment, Payment.enrollment_id == Enrollment.id)
        .where(*own, Payment.status == CONFIRMED)
        .group_by(Cohort.instructor_id)
    )
    for i, total in r_income.all():
        stats[i]["income"] = money(total)
    r_paid = await db.execute(
        select(InstructorPayout.instructor_id, func.coalesce(func.sum(InstructorPayout.amount), 0))
        .join(Cohort, Cohort.id == InstructorPayout.cohort_id)
        .where(InstructorPayout.instructor_id.in_(instructor_ids), *cohort_where)
        .group_by(InstructorPayout.instructor_id)
    )
    for i, total in r_paid.all():
        stats[i]["paid_out"] = money(total)
    return stats


def _payout_out(po: InstructorPayout) -> dict[str, Any]:
    return {
        "id": po.id,
        "version": po.version,
        "amount": po.amount,
        "paid_at": po.paid_at,
        "method": po.method,
        "note": po.note,
    }


async def salary_rows(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    *,
    instructor_id: uuid.UUID | None = None,
    on: date | None = None,
) -> list[dict[str, Any]]:
    """The payout schedule: one row per cohort × month it runs (cohorts without an instructor or
    cancelled have none), with the payout made for it, if any."""
    on = on or today()
    this_month = first_of_month(on)
    where = [Cohort.instructor_id.is_not(None), Cohort.status != CANCELLED, *cohort_where]
    if instructor_id is not None:
        where.append(Cohort.instructor_id == instructor_id)
    cohorts = (
        await db.execute(
            select(Cohort, AppUser.full_name, Course.name)
            .join(AppUser, AppUser.id == Cohort.instructor_id)
            .join(Course, Course.id == Cohort.course_id)
            .where(*where)
            .order_by(AppUser.full_name, Cohort.code)
        )
    ).all()
    payouts: dict[tuple[uuid.UUID, uuid.UUID, date], InstructorPayout] = {}
    if cohorts:
        found = await db.execute(
            select(InstructorPayout).where(
                InstructorPayout.cohort_id.in_([c.id for c, _, _ in cohorts])
            )
        )
        payouts = {(po.instructor_id, po.cohort_id, po.period): po for po in found.scalars()}
    rows: list[dict[str, Any]] = []
    for c, instructor, course in cohorts:
        for period in cohort_periods(c.start_date, c.end_date):
            po = payouts.get((c.instructor_id, c.id, period))  # type: ignore[arg-type]
            paid = po.amount if po else ZERO
            due = max(c.instructor_rate - paid, ZERO)
            if po and due == 0:
                state = "выплачено"
            elif po:
                state = "частично"
            else:
                state = "к выплате" if period <= this_month else "запланировано"
            rows.append(
                {
                    "instructor_id": c.instructor_id,
                    "instructor_name": instructor,
                    "cohort_id": c.id,
                    "cohort_version": c.version,
                    "cohort_code": c.code,
                    "course_name": course,
                    "branch_id": c.branch_id,
                    "period": period,
                    "rate": c.instructor_rate,
                    "paid": paid,
                    "due": due,
                    "state": state,
                    "payout": _payout_out(po) if po else None,
                }
            )
    return rows


async def salary_summary(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    rows: list[dict[str, Any]],
    *,
    instructor_id: uuid.UUID | None = None,
    on: date | None = None,
) -> dict[str, Any]:
    """Fund per month, total by schedule, paid (all payouts made, scheduled or not), due."""
    this_month = first_of_month(on or today())
    extra = [InstructorPayout.instructor_id == instructor_id] if instructor_id else []
    paid_total = await payroll_total(db, cohort_where, *extra)
    paid_month = await payroll_total(
        db, cohort_where, InstructorPayout.period == this_month, *extra
    )
    now = [r for r in rows if r["period"] == this_month]
    return {
        "month": this_month,
        "fund_month": sum((r["rate"] for r in now), ZERO),
        "total_schedule": sum((r["rate"] for r in rows), ZERO),
        "paid_total": paid_total,
        "paid_month": paid_month,
        "due_month": sum((r["due"] for r in now), ZERO),
        "overdue": sum((r["due"] for r in rows if r["period"] < this_month), ZERO),
    }


__all__ = [
    "cohort_income",
    "cohort_months",
    "cohort_payers",
    "cohort_periods",
    "debt_of",
    "enrollment_money",
    "expected_months",
    "finance",
    "income_total",
    "instructor_stats",
    "payment_totals",
    "payroll_total",
    "salary_rows",
    "salary_summary",
]
