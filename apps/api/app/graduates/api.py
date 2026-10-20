"""Graduates: by students, by courses, certificates (stage 4).

Rights: `graduates` view / change; the instructor role has no access. Branch scope applies.
The list, the Excel files and the dashboard's «Выпускники» tile share `graduate_where`; score,
paid and employment come from `app.metrics`.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, text

from app.audit.log import record
from app.auth.deps import Principal, require_csrf_header
from app.cohorts.status import GRADUATE
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.graduates.errors import CERTIFICATE_ISSUED, NOT_GRADUATE
from app.leads.scope import reader, writer
from app.metrics.reports import (
    Scope,
    graduate_count,
    graduate_rows,
    graduate_where,
    graduates_by_course,
)
from app.models import Cohort, Enrollment, Student

router = APIRouter(
    prefix="/api/v1/graduates", tags=["graduates"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, reader("graduates")]
Change = Annotated[Principal, writer("graduates")]


def _where(
    p: Principal,
    branch_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    **filters: Any,
) -> list[Any]:
    if branch_id:
        p.check_scope(branch_id)
    return graduate_where(Scope.of(p, branch_id), date_from, date_to, **filters)


@router.get("/students")
async def graduates_by_students(
    p: View,
    db: DB,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    instructor_id: uuid.UUID | None = None,
    employed: bool | None = None,
    certificate: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    where = _where(
        p, branch_id, date_from, date_to, course_id=course_id, instructor_id=instructor_id,
        employed=employed, certificate=certificate, q=q,
    )  # fmt: skip
    total = await graduate_count(db, where)
    rows = await graduate_rows(db, where, MAX_ROWS)
    start = (page - 1) * page_size
    return {
        "items": rows[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


STUDENT_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Студент", lambda r: r["student_name"]),
    Col("Телефон", lambda r: r["phone"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Поток", lambda r: r["cohort_code"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Инструктор", lambda r: r["instructor_name"]),
    Col("Зачислен", lambda r: r["enrolled_at"], "date"),
    Col("Итоговый балл", lambda r: r["score"], "int"),
    Col("Оплачено", lambda r: r["paid"], "money"),
    Col("Сертификат", lambda r: r["certificate_no"]),
    Col("Трудоустроен", lambda r: r["employed"], "bool"),
    Col("Организация", lambda r: r["organization"]),
]


@router.get("/students/export")
async def export_graduates_by_students(
    p: View,
    db: DB,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    instructor_id: uuid.UUID | None = None,
    employed: bool | None = None,
    certificate: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    where = _where(
        p, branch_id, date_from, date_to, course_id=course_id, instructor_id=instructor_id,
        employed=employed, certificate=certificate, q=q,
    )  # fmt: skip
    rows = await graduate_rows(db, where, MAX_ROWS + 1)
    check_cap(rows)
    return await xlsx_response(
        db,
        p,
        entity="graduate",
        slug="vypuskniki",
        title="Выпускники",
        columns=STUDENT_COLUMNS,
        rows=rows,
        filters={
            "q": q, "branch_id": branch_id, "course_id": course_id, "instructor_id": instructor_id,
            "date_from": date_from, "date_to": date_to,
        },
    )  # fmt: skip


async def _course_rows(
    db: DB, p: Principal, branch_id: uuid.UUID | None, date_from: date | None, date_to: date | None
) -> list[dict[str, Any]]:
    return graduates_by_course(
        await graduate_rows(db, _where(p, branch_id, date_from, date_to), MAX_ROWS + 1)
    )


@router.get("/courses")
async def graduates_by_courses(
    p: View,
    db: DB,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    return {"items": await _course_rows(db, p, branch_id, date_from, date_to)}


COURSE_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Курс", lambda r: r["course_name"]),
    Col("Выпускников", lambda r: r["graduates"], "int"),
    Col("Средний балл", lambda r: r["avg_score"]),
    Col("Трудоустроено", lambda r: r["employed"], "int"),
    Col("Трудоустроено, %", lambda r: r["employed_percent"], "percent"),
]


@router.get("/courses/export")
async def export_graduates_by_courses(
    p: View,
    db: DB,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    rows = await _course_rows(db, p, branch_id, date_from, date_to)
    return await xlsx_response(
        db,
        p,
        entity="graduate_course",
        slug="vypuskniki_po_kursam",
        title="Выпускники по курсам",
        columns=COURSE_COLUMNS,
        rows=rows,
        filters={"branch_id": branch_id, "date_from": date_from, "date_to": date_to},
    )


@router.post("/{enrollment_id}/certificate")
async def issue_certificate(enrollment_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    """CERT-YYYY-NNNN from `certificate_no_seq`, for a graduate enrollment, once."""
    row = (
        await db.execute(
            select(Enrollment, Student, Cohort)
            .join(Student, Student.id == Enrollment.student_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(Enrollment.id == enrollment_id)
            .with_for_update(of=Enrollment)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    enrollment, student, cohort = row
    p.check_scope(cohort.branch_id)
    if enrollment.status != GRADUATE:
        raise DomainError(NOT_GRADUATE)
    if enrollment.certificate_no:
        raise DomainError(CERTIFICATE_ISSUED)
    now = datetime.now(UTC)
    n = (await db.execute(text("SELECT nextval('certificate_no_seq')"))).scalar_one()
    enrollment.certificate_no = f"CERT-{now.year}-{n:04d}"
    enrollment.certificate_issued_at = now
    await db.flush()
    await record(
        db,
        p.id,
        "enrollment.certificate",
        "enrollment",
        enrollment.id,
        {"certificate_no": [None, enrollment.certificate_no], "cohort": [None, cohort.code]},
        branch_id=cohort.branch_id,
    )
    return {
        "enrollment_id": enrollment.id,
        "student_name": student.full_name,
        "certificate_no": enrollment.certificate_no,
        "certificate_issued_at": enrollment.certificate_issued_at,
    }
