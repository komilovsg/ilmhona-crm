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


# (enrollment id, enrolled_at, status, cohort price_month, cohort start, cohort end)
MoneyRow = tuple[uuid.UUID, datetime, str, Decimal, date, date]


async def enrollment_money(
    db: AsyncSession, rows: Sequence[tuple[Enrollment, Cohort]], on: date | None = None
) -> dict[uuid.UUID, dict[str, Any]]:
    """paid, paid months, expected and debt per enrollment (every given enrollment is present)."""
    return await enrollment_money_rows(
        db,
        [(e.id, e.enrolled_at, e.status, c.price_month, c.start_date, c.end_date) for e, c in rows],
        on,
    )


async def enrollment_money_rows(
    db: AsyncSession, rows: Sequence[MoneyRow], on: date | None = None
) -> dict[uuid.UUID, dict[str, Any]]:
    """Same as `enrollment_money` from plain columns: lists of hundreds of enrollments (debtors)
    skip building the ORM objects."""
    on = on or today()
    ids = [r[0] for r in rows]
    # one statement: per enrollment and month, everything entered / confirmed / pending
    entered: dict[uuid.UUID, dict[int, Decimal]] = {i: {} for i in ids}
    confirmed: dict[uuid.UUID, dict[int, Decimal]] = {i: {} for i in ids}
    pending: dict[uuid.UUID, dict[int, Decimal]] = {i: {} for i in ids}
    if ids:
        result = await db.execute(
            select(
                Payment.enrollment_id,
                Payment.month_no,
                func.sum(Payment.amount),
                func.coalesce(func.sum(Payment.amount).filter(Payment.status == CONFIRMED), 0),
                func.coalesce(func.sum(Payment.amount).filter(Payment.status == PENDING), 0),
            )
            .where(Payment.enrollment_id.in_(ids))
            .group_by(Payment.enrollment_id, Payment.month_no)
        )
        for i, m, total_m, confirmed_m, pending_m in result.all():
            entered[i][m] = money(total_m)
            pending[i][m] = money(pending_m)
            if confirmed_m:
                confirmed[i][m] = money(confirmed_m)
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for eid, enrolled_at, status, price, start, end in rows:
        total = money(sum(confirmed[eid].values(), ZERO))
        months = sorted(confirmed[eid])
        local = enrolled_at.astimezone(TZ).date()
        expected = price * expected_months(local, start, end, on)
        states = [
            month_info(m, entered[eid].get(m, ZERO), pending[eid].get(m, ZERO), price)
            for m in range(1, cohort_months(start, end) + 1)
        ]
        owed = owed_month_numbers(enrolled_at, start, end, on)
        out[eid] = {
            "paid": total,
            "paid_months": months,
            "expected": expected,
            "debt": debt_of(expected, total, status),
            "month_states": states,
            # months started so far that are not covered yet, with what is left of each
            "due_months": []
            if status == EXPELLED
            else [
                {"month_no": st["month_no"], "remaining": st["remaining"]}
                for st in states
                if st["month_no"] in owed and st["state"] != MONTH_PAID
            ],
        }
    return out


MONTH_UNPAID, MONTH_PARTIAL, MONTH_PAID = "не оплачен", "частично", "оплачен"


def month_info(month_no: int, entered: Decimal, pending: Decimal, price: Decimal) -> dict[str, Any]:
    """The state of one month of an enrollment (pending + confirmed count, like the payment rule):
    оплачен (reaches the price), частично (something, less than the price), не оплачен."""
    if month_full(entered, price) or (price <= 0 and entered > 0):
        state = MONTH_PAID
    elif entered > 0:
        state = MONTH_PARTIAL
    else:
        state = MONTH_UNPAID
    return {
        "month_no": month_no,
        "paid": entered,
        "pending": pending,
        "price": price,
        "remaining": max(price - entered, ZERO),
        "state": state,
    }


def owed_month_numbers(enrolled_at: datetime, start: date, end: date, on: date) -> range:
    """`month_no`s the student has started so far (the months `expected_months` counts)."""
    first_index = month_index(start)
    first = max(month_index(enrolled_at.astimezone(TZ).date()), first_index)
    last = min(month_index(on), month_index(end))
    return range(first - first_index + 1, last - first_index + 2)


async def month_sums(
    db: AsyncSession,
    enrollment_ids: Sequence[uuid.UUID],
    *,
    exclude: uuid.UUID | None = None,
    status: str | None = None,
) -> dict[uuid.UUID, dict[int, Decimal]]:
    """What is entered per enrollment and month: pending + confirmed (a month is «taken» as soon
    as a payment for it exists, confirmed or not). `exclude` leaves one payment out (an edit);
    `status` sums only that status."""
    if not enrollment_ids:
        return {}
    where: list[ColumnElement[bool]] = [Payment.enrollment_id.in_(enrollment_ids)]
    if exclude is not None:
        where.append(Payment.id != exclude)
    if status is not None:
        where.append(Payment.status == status)
    rows = await db.execute(
        select(Payment.enrollment_id, Payment.month_no, func.sum(Payment.amount))
        .where(*where)
        .group_by(Payment.enrollment_id, Payment.month_no)
    )
    out: dict[uuid.UUID, dict[int, Decimal]] = {i: {} for i in enrollment_ids}
    for eid, month_no, total in rows.all():
        out[eid][month_no] = money(total)
    return out


def month_full(entered: Decimal, price: Decimal) -> bool:
    """A month is full when what is entered for it reaches the price. A cohort without a price
    (0, an imported one waiting for review) has no cap: nothing is ever full."""
    return price > 0 and entered >= price


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


def _income_stmt(cohort_where: Sequence[ColumnElement[bool]], *extra: ColumnElement[bool]) -> Any:
    return (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .select_from(Payment)
        .join(Enrollment, Enrollment.id == Payment.enrollment_id)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .where(Payment.status == CONFIRMED, *cohort_where, *extra)
    )


def _payroll_stmt(cohort_where: Sequence[ColumnElement[bool]], *extra: ColumnElement[bool]) -> Any:
    return (
        select(func.coalesce(func.sum(InstructorPayout.amount), 0))
        .select_from(InstructorPayout)
        .join(Cohort, Cohort.id == InstructorPayout.cohort_id)
        .where(*cohort_where, *extra)
    )


def _ads_stmt(
    campaign_where: Sequence[ColumnElement[bool]],
    since: date | None = None,
    until: date | None = None,
) -> Any:
    where = list(campaign_where)
    if since:
        where.append(Campaign.start_date >= since)
    if until:
        where.append(Campaign.start_date <= until)
    return select(func.coalesce(func.sum(Campaign.budget), 0)).select_from(Campaign).where(*where)


async def income_total(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    *extra: ColumnElement[bool],
) -> Decimal:
    return money((await db.execute(_income_stmt(cohort_where, *extra))).scalar_one())


async def payroll_total(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    *extra: ColumnElement[bool],
) -> Decimal:
    """Расходы ЗП (#9): the payouts actually made."""
    return money((await db.execute(_payroll_stmt(cohort_where, *extra))).scalar_one())


async def ads_total(
    db: AsyncSession,
    campaign_where: Sequence[ColumnElement[bool]],
    since: date | None = None,
    until: date | None = None,
) -> Decimal:
    """Реклама: the budgets of the campaigns that started in the period (all, with no period)."""
    return money((await db.execute(_ads_stmt(campaign_where, since, until))).scalar_one())


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
    # the three sums in one round trip
    row = (
        await db.execute(
            select(
                _income_stmt(cohort_where, *paid).scalar_subquery(),
                _payroll_stmt(cohort_where, *payouts).scalar_subquery(),
                _ads_stmt(campaign_where, since, until).scalar_subquery(),
            )
        )
    ).one()
    income, payroll, ads = (money(v) for v in row)
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
    "enrollment_money_rows",
    "expected_months",
    "finance",
    "income_total",
    "instructor_stats",
    "month_full",
    "month_sums",
    "payment_totals",
    "payroll_total",
    "salary_rows",
    "salary_summary",
]
