"""Donor numbers: who pays for the students, and the report a donor gets.

- Funding of an enrollment: «донор» when a donor pays for it, «бесплатно» in a free cohort or
  when marked «не платит» (no donor's student), else «платник». `funding_counts` = enrollments
  of each kind among the enrolled (not expelled).
- Donor report: per donor and cohort, the donor's students: enrolled (all of them), studying
  (активный), completed (завершил), expelled (отчислен), graduated (выпускник), employed (the
  student has an employment record, the one employment table #13). Only students: the donor's
  money is not tracked.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, case, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, Cohort, Course, Donor, Employment, Enrollment

EXPELLED = "отчислен"
PAYING, BY_DONOR, FREE_SEAT = "paying", "donor", "free"


def funding_kind() -> ColumnElement[str]:
    """«paying» | «donor» | «free» of an enrollment (joined with its cohort)."""
    return case(
        (Enrollment.donor_id.is_not(None), literal(BY_DONOR)),
        (Cohort.funding == "бесплатный", literal(FREE_SEAT)),
        (Enrollment.not_paying, literal(FREE_SEAT)),
        else_=literal(PAYING),
    )


async def funding_counts(
    db: AsyncSession, cohort_where: Sequence[ColumnElement[bool]]
) -> dict[str, int]:
    """{paying, donor, free}: enrolled (not expelled) students of each kind in the scope."""
    kind = funding_kind()
    rows = await db.execute(
        select(kind, func.count())
        .select_from(Enrollment)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .where(*cohort_where, Enrollment.status != EXPELLED)
        .group_by(kind)
    )
    got = dict(rows.all())
    return {k: got.get(k, 0) for k in (PAYING, BY_DONOR, FREE_SEAT)}


async def cohort_funding_counts(
    db: AsyncSession, cohort_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """`funding_counts` per cohort."""
    out = {c: {PAYING: 0, BY_DONOR: 0, FREE_SEAT: 0} for c in cohort_ids}
    if not cohort_ids:
        return out
    kind = funding_kind()
    rows = await db.execute(
        select(Enrollment.cohort_id, kind, func.count())
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .where(Enrollment.cohort_id.in_(cohort_ids), Enrollment.status != EXPELLED)
        .group_by(Enrollment.cohort_id, kind)
    )
    for cid, k, n in rows.all():
        out[cid][k] = n
    return out


def _count(status: str) -> Any:
    return func.count().filter(Enrollment.status == status)


async def donor_report(
    db: AsyncSession,
    cohort_where: Sequence[ColumnElement[bool]],
    donor_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """One row per donor × cohort (donors by name, cohorts newest first)."""
    where = [*cohort_where]
    if donor_id is not None:
        where.append(Enrollment.donor_id == donor_id)
    employed = exists().where(Employment.student_id == Enrollment.student_id)
    rows = await db.execute(
        select(
            Donor.id,
            Donor.name,
            Cohort.id,
            Cohort.code,
            Course.name,
            Branch.name,
            Cohort.start_date,
            Cohort.end_date,
            Cohort.status,
            func.count(),
            _count("активный"),
            _count("завершил"),
            _count(EXPELLED),
            _count("выпускник"),
            func.count().filter(employed),
        )
        .select_from(Enrollment)
        .join(Donor, Donor.id == Enrollment.donor_id)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .join(Course, Course.id == Cohort.course_id)
        .join(Branch, Branch.id == Cohort.branch_id)
        .where(*where)
        .group_by(Donor.id, Donor.name, Cohort.id, Course.name, Branch.name)
        .order_by(Donor.name, Cohort.start_date.desc(), Cohort.code)
    )
    return [
        {
            "donor_id": did,
            "donor_name": dname,
            "cohort_id": cid,
            "cohort_code": code,
            "course_name": course,
            "branch_name": branch,
            "start_date": start,
            "end_date": end,
            "cohort_status": status,
            "enrolled": enrolled,
            "studying": studying,
            "completed": completed,
            "expelled": expelled,
            "graduated": graduated,
            "employed": n_employed,
        }
        for (
            did, dname, cid, code, course, branch, start, end, status,
            enrolled, studying, completed, expelled, graduated, n_employed,
        ) in rows.all()
    ]  # fmt: skip


COUNTS = ("enrolled", "studying", "completed", "expelled", "graduated", "employed")


def donor_totals(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The report's rows summed per donor (the same rows, so they always add up)."""
    by: dict[uuid.UUID, dict[str, Any]] = {}
    for r in rows:
        t = by.setdefault(
            r["donor_id"],
            {"donor_id": r["donor_id"], "donor_name": r["donor_name"], "cohorts": 0}
            | dict.fromkeys(COUNTS, 0),
        )
        t["cohorts"] += 1
        for k in COUNTS:
            t[k] += r[k]
    return list(by.values())
