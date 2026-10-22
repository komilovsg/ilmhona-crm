"""Report numbers (SPEC «Метрики», stage 4): dashboard, master list, graduates, employment.

The dashboard, the lists and the Excel files take their numbers from here and from the other
`app.metrics` modules only, with the same `where` clauses as the lists, so they cannot disagree
(#3, #22).

- Scope = the user's rights (branch, instructor) plus the branch toggle (Все / one branch).
- Period (`since` / `until`) cuts what has a date of its own: leads by creation day, income and
  payroll by payment day, ads by campaign start, graduates by the end of their cohort. «Now»
  numbers (active students, students in the base, active cohorts, на наборе) ignore it.
- Overview: leads + conversion, students (active / in the base), cohorts (active / на наборе),
  income / payroll / ads / profit, campaigns, graduates, CAC = ads ÷ converted leads (None when
  there are none: «—»).
- By month: the last 12 calendar months, this one included; every figure is the sum of the same
  rows the matching list shows for that month (income = confirmed payments by `paid_at`, payroll =
  payouts by `paid_at`, ads = campaign budgets by start date, new students and leads by creation
  day in Dushanbe time). Profit = income − ads − payroll.
- By course: cohorts, income, students (not expelled, distinct), graduates.
- Master list (per cohort): leads = leads of the cohort's course and branch created from 45 days
  before the start through the start day; zero lesson = those with status «нулевой урок» or later
  («записан»); enrolled = not expelled; paid month 1/2/3 = enrollments with a confirmed payment of
  that month; LTV/чел = income ÷ enrolled; graduates = enrollments «выпускник»; employed =
  graduates whose student has an employment record.
- Graduates: enrollments «выпускник». Score = attendance + homework + final (`enrollment_results`),
  paid = confirmed sum, employed = the student has an employment record (the only table, #13).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, DateTime, cast, exists, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal
from app.education.scope import cohort_filters, student_filters
from app.export import Col
from app.leads.query import lead_where
from app.leads.scope import campaign_filters
from app.metrics import cohort_counts, cohort_enrolled, enrollment_results, student_counts
from app.metrics.money import (
    CONFIRMED,
    EXPELLED,
    TZ,
    ZERO,
    cohort_income,
    enrollment_money,
    finance,
    money,
    today,
)
from app.metrics.sales import (
    CONVERTED,
    callback_filter,
    funnel,
    percent,
    ratio,
)
from app.models import (
    AppUser,
    Branch,
    Campaign,
    Cohort,
    Course,
    Employment,
    Enrollment,
    InstructorPayout,
    Lead,
    Payment,
    Student,
)
from app.permissions import allows

GRADUATE = "выпускник"
LEAD_WINDOW_DAYS = 45
ZERO_LESSON_OR_LATER = ("нулевой урок", CONVERTED)
MONTHS = 12

# Money a report shows only to who may view the section it comes from: income (and LTV, paid)
# ⇐ Оплаты, payroll ⇐ Инструкторы и зарплаты, ads and CAC ⇐ Маркетинг, profit ⇐ all three.
# Hidden = null in JSON and no column in Excel.
MONEY_SECTIONS: dict[str, tuple[str, ...]] = {
    "income": ("payments",),
    "ltv": ("payments",),
    "paid": ("payments",),
    "payroll": ("instructors",),
    "ads": ("marketing",),
    "cac": ("marketing",),
    "profit": ("payments", "instructors", "marketing"),
}


def hidden_money(p: Principal) -> set[str]:
    return {
        key
        for key, sections in MONEY_SECTIONS.items()
        if not all(allows(p.level(s), "view") for s in sections)
    }


def hide_money[R: dict[str, Any]](rows: list[R], hidden: set[str]) -> list[R]:
    for row in rows:
        for key in hidden & row.keys():
            row[key] = None
    return rows


def shown_columns[T](
    columns: list[Col[T]], money: dict[str, str], hidden: set[str]
) -> list[Col[T]]:
    """`columns` without those whose key (`money`: header -> key) is hidden."""
    return [c for c in columns if money.get(c.header, "") not in hidden]


@dataclass
class Scope:
    """What a report may count: the user's scope plus the branch toggle."""

    p: Principal
    branch_id: uuid.UUID | None = None
    cohort: list[ColumnElement[bool]] = field(default_factory=list)
    campaign: list[ColumnElement[bool]] = field(default_factory=list)
    student: list[ColumnElement[bool]] = field(default_factory=list)

    @classmethod
    def of(cls, p: Principal, branch_id: uuid.UUID | None) -> Scope:
        s = cls(p, branch_id)
        s.cohort = cohort_filters(p)
        s.campaign = campaign_filters(p)
        s.student = student_filters(p)
        if branch_id:
            s.cohort.append(Cohort.branch_id == branch_id)
            s.campaign.append(Campaign.branch_id == branch_id)
            s.student.append(Student.branch_id == branch_id)
        return s

    def leads(self, since: date | None = None, until: date | None = None) -> list[Any]:
        return lead_where(self.p, branch_id=self.branch_id, date_from=since, date_to=until)


def _in_period(column: Any, since: date | None, until: date | None) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = []
    if since:
        where.append(column >= since)
    if until:
        where.append(column <= until)
    return where


# ---- graduates ---------------------------------------------------------------------------


def employed_expr() -> ColumnElement[bool]:
    """The enrollment's student has an employment record."""
    return exists().where(Employment.student_id == Enrollment.student_id)


def graduate_where(
    scope: Scope,
    since: date | None = None,
    until: date | None = None,
    *,
    course_id: uuid.UUID | None = None,
    instructor_id: uuid.UUID | None = None,
    employed: bool | None = None,
    certificate: bool | None = None,
    q: str | None = None,
) -> list[ColumnElement[bool]]:
    """The one `where` of graduates: the dashboard count, both lists and the Excel files."""
    where: list[ColumnElement[bool]] = [
        Enrollment.status == GRADUATE,
        *scope.cohort,
        *_in_period(Cohort.end_date, since, until),
    ]
    if course_id:
        where.append(Cohort.course_id == course_id)
    if instructor_id:
        where.append(Cohort.instructor_id == instructor_id)
    if employed is not None:
        where.append(employed_expr() if employed else ~employed_expr())
    if certificate is not None:
        where.append(
            Enrollment.certificate_no.is_not(None)
            if certificate
            else Enrollment.certificate_no.is_(None)
        )
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(Student.full_name.ilike(like) | Student.phone.ilike(like))
    return where


def _graduate_select(query: Any) -> Any:
    return (
        query.select_from(Enrollment)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .join(Student, Student.id == Enrollment.student_id)
        .join(Course, Course.id == Cohort.course_id)
        .outerjoin(AppUser, AppUser.id == Cohort.instructor_id)
    )


async def graduate_count(db: AsyncSession, where: Sequence[ColumnElement[bool]]) -> int:
    count: int = (
        await db.execute(_graduate_select(select(func.count(Enrollment.id))).where(*where))
    ).scalar_one()
    return count


async def graduate_rows(
    db: AsyncSession,
    where: Sequence[ColumnElement[bool]],
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """One row per graduate enrollment, with score, paid, certificate and employment."""
    query = (
        _graduate_select(
            select(Enrollment, Student, Cohort, Course.name, AppUser.full_name, Branch.name)
        )
        .join(Branch, Branch.id == Cohort.branch_id)
        .where(*where)
        .order_by(Student.full_name, Enrollment.id)
    )
    if limit:
        query = query.limit(limit).offset(offset)
    found = (await db.execute(query)).all()
    # one query for the enrollments of every cohort together, not one per cohort
    results = await enrollment_results(db, None, enrollment_ids=[e.id for e, *_ in found])
    paid = await enrollment_money(db, [(e, c) for e, _, c, *_ in found])
    students = list({s.id for _, s, *_ in found})
    jobs: dict[uuid.UUID, list[Employment]] = {}
    if students:
        for job in (
            (
                await db.execute(
                    select(Employment)
                    .where(Employment.student_id.in_(students))
                    .order_by(Employment.employed_at.desc(), Employment.created_at.desc())
                )
            )
            .scalars()
            .all()
        ):
            jobs.setdefault(job.student_id, []).append(job)
    rows: list[dict[str, Any]] = []
    for e, s, c, course, instructor, branch in found:
        own = jobs.get(s.id, [])
        res = results[e.id]
        # an old total that came without homework / final stands until real grades exist
        legacy = e.legacy_total is not None and res["homework"] is None and res["final"] is None
        rows.append(
            {
                "enrollment_id": e.id,
                "enrollment_version": e.version,
                "student_id": s.id,
                "student_name": s.full_name,
                "phone": s.phone,
                "branch_id": c.branch_id,
                "branch_name": branch,
                "cohort_id": c.id,
                "cohort_code": c.code,
                "course_id": c.course_id,
                "course_name": course,
                "instructor_name": instructor,
                "enrolled_at": e.enrolled_at,
                "cohort_end": c.end_date,
                "score": round(e.legacy_total) if legacy else res["total"],
                "score_legacy": legacy,
                "paid": paid[e.id]["paid"],
                "certificate_no": e.certificate_no,
                "certificate_issued_at": e.certificate_issued_at,
                "employed": bool(own),
                "organization": own[0].organization if own else None,
                "employed_at": own[0].employed_at if own else None,
            }
        )
    return rows


def graduates_by_course(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count, average score and employed % per course, from the same rows as the student view."""
    groups: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r["course_id"], []).append(r)
    out = []
    for course_id, items in groups.items():
        employed = sum(1 for r in items if r["employed"])
        out.append(
            {
                "course_id": course_id,
                "course_name": items[0]["course_name"],
                "graduates": len(items),
                "avg_score": round(sum(r["score"] for r in items) / len(items), 1),
                "employed": employed,
                "employed_percent": percent(employed, len(items)),
            }
        )
    return sorted(out, key=lambda r: r["course_name"])


# ---- dashboard ---------------------------------------------------------------------------


async def overview(
    db: AsyncSession, scope: Scope, since: date | None, until: date | None
) -> dict[str, Any]:
    leads = await funnel(db, scope.leads(since, until))
    fin = await finance(db, scope.cohort, scope.campaign, since, until)
    cohorts = await cohort_counts(db, scope.cohort)
    students = await student_counts(db, scope.student)
    # campaigns and graduates: two counts in one round trip
    campaigns, graduates = (
        await db.execute(
            select(
                select(func.count())
                .select_from(Campaign)
                .where(*scope.campaign, *_in_period(Campaign.start_date, since, until))
                .scalar_subquery(),
                _graduate_select(select(func.count(Enrollment.id)))
                .where(*graduate_where(scope, since, until))
                .scalar_subquery(),
            )
        )
    ).one()
    converted = leads["counts"][CONVERTED]
    return {
        "leads": leads["counts"]["всего"],
        "conversion": leads["conversion"],
        "funnel": leads["counts"],
        "active_students": students["активный"],
        "students_total": students["всего"],
        "income": fin["income"],
        "active_cohorts": cohorts["активный"],
        "recruiting_cohorts": cohorts["набор"],
        "cohorts_total": cohorts["всего"],
        "payroll": fin["payroll"],
        "profit": fin["profit"],
        "ads": fin["ads"],
        "campaigns": campaigns,
        "graduates": graduates,
        "converted": converted,
        "cac": ratio(fin["ads"], converted),
    }


def month_list(on: date | None = None, n: int = MONTHS) -> list[date]:
    """First days of the last `n` months, the month of `on` (today) last."""
    on = on or today()
    index = on.year * 12 + on.month - 1
    return [date((index - i) // 12, (index - i) % 12 + 1, 1) for i in range(n - 1, -1, -1)]


def month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _ym(column: Any) -> Any:
    return func.to_char(column, literal_column("'YYYY-MM'"))


def _ym_local(column: Any) -> Any:
    return func.to_char(
        func.timezone(literal_column("'Asia/Dushanbe'"), column), literal_column("'YYYY-MM'")
    )


async def by_month(db: AsyncSession, scope: Scope, on: date | None = None) -> dict[str, Any]:
    months = month_list(on)
    since, until = months[0], month_end(months[-1])
    paid = _in_period(Payment.paid_at, since, until)
    income = await db.execute(
        select(_ym(Payment.paid_at), func.coalesce(func.sum(Payment.amount), 0))
        .select_from(Payment)
        .join(Enrollment, Enrollment.id == Payment.enrollment_id)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .where(Payment.status == CONFIRMED, *scope.cohort, *paid)
        .group_by(_ym(Payment.paid_at))
    )
    payroll = await db.execute(
        select(_ym(InstructorPayout.paid_at), func.coalesce(func.sum(InstructorPayout.amount), 0))
        .join(Cohort, Cohort.id == InstructorPayout.cohort_id)
        .where(*scope.cohort, *_in_period(InstructorPayout.paid_at, since, until))
        .group_by(_ym(InstructorPayout.paid_at))
    )
    ads = await db.execute(
        select(_ym(Campaign.start_date), func.coalesce(func.sum(Campaign.budget), 0))
        .where(*scope.campaign, *_in_period(Campaign.start_date, since, until))
        .group_by(_ym(Campaign.start_date))
    )
    students = await db.execute(
        select(_ym_local(Student.created_at), func.count())
        .where(
            *scope.student,
            Student.created_at >= datetime.combine(since, datetime.min.time(), tzinfo=TZ),
            Student.created_at
            < datetime.combine(until + timedelta(days=1), datetime.min.time(), tzinfo=TZ),
        )
        .group_by(_ym_local(Student.created_at))
    )
    leads = await db.execute(
        select(_ym_local(Lead.created_at), func.count())
        .where(*scope.leads(since, until))
        .group_by(_ym_local(Lead.created_at))
    )
    inc, pay, ad = ({k: money(v) for k, v in r.all()} for r in (income, payroll, ads))
    stu: dict[str, int] = dict(students.all())
    led: dict[str, int] = dict(leads.all())
    items = []
    for first in months:
        key = f"{first:%Y-%m}"
        i, p_, a = inc.get(key, ZERO), pay.get(key, ZERO), ad.get(key, ZERO)
        items.append(
            {
                "month": first,
                "income": i,
                "payroll": p_,
                "ads": a,
                "profit": i - a - p_,
                "new_students": stu.get(key, 0),
                "leads": led.get(key, 0),
            }
        )
    return {"since": since, "until": until, "items": items}


async def by_course(
    db: AsyncSession, scope: Scope, since: date | None, until: date | None
) -> list[dict[str, Any]]:
    cohorts = dict(
        (
            await db.execute(
                select(Cohort.course_id, func.count())
                .where(*scope.cohort)
                .group_by(Cohort.course_id)
            )
        ).all()
    )
    income = (
        await db.execute(
            select(Cohort.course_id, func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Enrollment, Enrollment.id == Payment.enrollment_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(
                Payment.status == CONFIRMED,
                *scope.cohort,
                *_in_period(Payment.paid_at, since, until),
            )
            .group_by(Cohort.course_id)
        )
    ).all()
    students = (
        await db.execute(
            select(Cohort.course_id, func.count(func.distinct(Enrollment.student_id)))
            .select_from(Enrollment)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(Enrollment.status != EXPELLED, *scope.cohort)
            .group_by(Cohort.course_id)
        )
    ).all()
    grads = (
        await db.execute(
            _graduate_select(select(Cohort.course_id, func.count(Enrollment.id)))
            .where(*graduate_where(scope, since, until))
            .group_by(Cohort.course_id)
        )
    ).all()
    names = dict((await db.execute(select(Course.id, Course.name))).all())
    inc, stu, gra = ({k: v for k, v in r} for r in (income, students, grads))
    items = [
        {
            "course_id": cid,
            "course_name": names[cid],
            "cohorts": cohorts[cid],
            "income": money(inc.get(cid, 0)),
            "students": stu.get(cid, 0),
            "graduates": gra.get(cid, 0),
        }
        for cid in cohorts
    ]
    return sorted(items, key=lambda r: (-r["income"], r["course_name"]))


async def callback_leads(db: AsyncSession, scope: Scope, limit: int = 5) -> list[dict[str, Any]]:
    """«Перезвонить сегодня»: the same filter the lead list's callback view uses."""
    rows = (
        await db.execute(
            select(Lead, Course.name)
            .outerjoin(Course, Course.id == Lead.course_id)
            .where(*scope.leads(), *callback_filter())
            .order_by(Lead.next_contact_at, Lead.id)
            .limit(limit)
        )
    ).all()
    return [_lead_item(lead, course) for lead, course in rows]


async def recent_leads(db: AsyncSession, scope: Scope, limit: int = 5) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Lead, Course.name)
            .outerjoin(Course, Course.id == Lead.course_id)
            .where(*scope.leads())
            .order_by(Lead.created_at.desc(), Lead.id)
            .limit(limit)
        )
    ).all()
    return [_lead_item(lead, course) for lead, course in rows]


def _lead_item(lead: Lead, course: str | None) -> dict[str, Any]:
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "phone": lead.phone,
        "status": lead.status,
        "course_name": course,
        "created_at": lead.created_at,
        "next_contact_at": lead.next_contact_at,
    }


# ---- master list -------------------------------------------------------------------------


def master_where(
    scope: Scope,
    status: str | None = None,
    since: date | None = None,
    until: date | None = None,
) -> list[ColumnElement[bool]]:
    """The one `where` of the master list (cohorts that start in the period)."""
    where = list(scope.cohort)
    if status:
        where.append(Cohort.status == status)
    where.extend(_in_period(Cohort.start_date, since, until))
    return where


def master_select(where: Sequence[ColumnElement[bool]]) -> Any:
    return (
        select(Cohort, Course.name, Course.format, Branch.name)
        .join(Course, Course.id == Cohort.course_id)
        .join(Branch, Branch.id == Cohort.branch_id)
        .where(*where)
        .order_by(Cohort.start_date.desc(), Cohort.code)
    )


async def master_count(db: AsyncSession, where: Sequence[ColumnElement[bool]]) -> int:
    return (await db.execute(select(func.count()).select_from(Cohort).where(*where))).scalar_one()


def _window_start(column: Any, days: int) -> Any:
    return func.timezone("Asia/Dushanbe", cast(column - days, DateTime))


async def master_rows(
    db: AsyncSession, found: Sequence[tuple[Cohort, str, str, str]]
) -> list[dict[str, Any]]:
    ids = [c.id for c, *_ in found]
    if not ids:
        return []
    windows = (
        await db.execute(
            select(
                Cohort.id,
                func.count(Lead.id),
                func.count(Lead.id).filter(Lead.status.in_(ZERO_LESSON_OR_LATER)),
            )
            .select_from(Cohort)
            .outerjoin(
                Lead,
                (Lead.course_id == Cohort.course_id)
                & (Lead.branch_id == Cohort.branch_id)
                & (Lead.created_at >= _window_start(Cohort.start_date, LEAD_WINDOW_DAYS))
                & (Lead.created_at < _window_start(Cohort.start_date, -1)),
            )
            .where(Cohort.id.in_(ids))
            .group_by(Cohort.id)
        )
    ).all()
    leads = {i: (n, z) for i, n, z in windows}
    month_paid = (
        await db.execute(
            select(Enrollment.cohort_id, Payment.month_no, func.count(func.distinct(Enrollment.id)))
            .join(Payment, Payment.enrollment_id == Enrollment.id)
            .where(
                Enrollment.cohort_id.in_(ids),
                Enrollment.status != EXPELLED,
                Payment.status == CONFIRMED,
                Payment.month_no.in_((1, 2, 3)),
            )
            .group_by(Enrollment.cohort_id, Payment.month_no)
        )
    ).all()
    paid = {(c, m): n for c, m, n in month_paid}
    grads = (
        await db.execute(
            select(Enrollment.cohort_id, func.count(), func.count().filter(employed_expr()))
            .where(Enrollment.cohort_id.in_(ids), Enrollment.status == GRADUATE)
            .group_by(Enrollment.cohort_id)
        )
    ).all()
    graduates = {c: (n, e) for c, n, e in grads}
    enrolled = await cohort_enrolled(db, ids)
    income = await cohort_income(db, ids)
    rows = []
    for c, course, fmt, branch in found:
        n_leads, n_zero = leads.get(c.id, (0, 0))
        g, employed = graduates.get(c.id, (0, 0))
        rows.append(
            {
                "cohort_id": c.id,
                "code": c.code,
                "branch_id": c.branch_id,
                "branch_name": branch,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "course_id": c.course_id,
                "course_name": course,
                "format": fmt,
                "price_month": c.price_month,
                "status": c.status,
                "leads": n_leads,
                "zero_lesson": n_zero,
                "enrolled": enrolled[c.id],
                "paid_1": paid.get((c.id, 1), 0),
                "paid_2": paid.get((c.id, 2), 0),
                "paid_3": paid.get((c.id, 3), 0),
                "income": income[c.id],
                "ltv": ratio(income[c.id], enrolled[c.id]),
                "graduates": g,
                "employed": employed,
            }
        )
    return rows


async def employment_rows_of(db: AsyncSession, student_id: uuid.UUID) -> list[Employment]:
    return list(
        (
            await db.execute(
                select(Employment)
                .where(Employment.student_id == student_id)
                .order_by(Employment.employed_at.desc())
            )
        )
        .scalars()
        .all()
    )


__all__ = [
    "Scope",
    "by_course",
    "by_month",
    "callback_leads",
    "employed_expr",
    "graduate_count",
    "graduate_rows",
    "graduate_where",
    "graduates_by_course",
    "hidden_money",
    "hide_money",
    "master_count",
    "master_rows",
    "master_select",
    "master_where",
    "month_list",
    "overview",
    "recent_leads",
    "shown_columns",
]
