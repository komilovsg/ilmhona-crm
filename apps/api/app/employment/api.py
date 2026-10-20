"""Employment (трудоустройство): the one table every screen reads (#13).

Rights: `graduates` view / change; the instructor role has no access. Branch scope by the
student's branch. A job is recorded for a graduate only; the optional enrollment names the course
that led to it.
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.education.scope import student_filters
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.graduates.errors import EMPLOYMENT_ENROLLMENT_MISMATCH, NOT_GRADUATE
from app.leads.scope import reader, writer
from app.metrics.reports import GRADUATE
from app.models import Branch, Cohort, Course, Employment, Enrollment, Student

router = APIRouter(
    prefix="/api/v1/employment", tags=["employment"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, reader("graduates")]
Change = Annotated[Principal, writer("graduates")]

Organization = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Position = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmploymentCreate(Strict):
    student_id: uuid.UUID
    enrollment_id: uuid.UUID | None = None
    organization: Organization
    position: Position | None = None
    employed_at: date


class EmploymentUpdate(Strict):
    enrollment_id: uuid.UUID | None = None
    organization: Organization | None = None
    position: Position | None = None
    employed_at: date | None = None


def _where(
    p: Principal,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = list(student_filters(p))
    if branch_id:
        p.check_scope(branch_id)
        where.append(Student.branch_id == branch_id)
    if course_id:
        where.append(Cohort.course_id == course_id)
    if student_id:
        where.append(Employment.student_id == student_id)
    if date_from:
        where.append(Employment.employed_at >= date_from)
    if date_to:
        where.append(Employment.employed_at <= date_to)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(
            or_(
                Student.full_name.ilike(like),
                Student.phone.ilike(like),
                Employment.organization.ilike(like),
            )
        )
    return where


def _select(where: list[ColumnElement[bool]]) -> Any:
    return (
        select(Employment, Student, Branch.name, Cohort.code, Course.name)
        .join(Student, Student.id == Employment.student_id)
        .join(Branch, Branch.id == Student.branch_id)
        .outerjoin(Enrollment, Enrollment.id == Employment.enrollment_id)
        .outerjoin(Cohort, Cohort.id == Enrollment.cohort_id)
        .outerjoin(Course, Course.id == Cohort.course_id)
        .where(*where)
        .order_by(Employment.employed_at.desc(), Employment.id)
    )


def _out(row: Any) -> dict[str, Any]:
    e, s, branch, code, course = row
    return {
        "id": e.id,
        "version": e.version,
        "student_id": s.id,
        "student_name": s.full_name,
        "phone": s.phone,
        "branch_name": branch,
        "enrollment_id": e.enrollment_id,
        "cohort_code": code,
        "course_name": course,
        "organization": e.organization,
        "position": e.position,
        "employed_at": e.employed_at,
    }


async def _one(db: AsyncSession, p: Principal, employment_id: uuid.UUID) -> Any:
    row = (await db.execute(_select([*_where(p), Employment.id == employment_id]))).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    return row


@router.get("")
async def list_employment(
    p: View,
    db: DB,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    where = _where(p, q, branch_id, course_id, student_id, date_from, date_to)
    total = (
        await db.execute(
            select(func.count())
            .select_from(Employment)
            .join(Student, Student.id == Employment.student_id)
            .outerjoin(Enrollment, Enrollment.id == Employment.enrollment_id)
            .outerjoin(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(*where)
        )
    ).scalar_one()
    rows = (await db.execute(_select(where).limit(page_size).offset((page - 1) * page_size))).all()
    return {"items": [_out(r) for r in rows], "total": total, "page": page, "page_size": page_size}


EMPLOYMENT_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Студент", lambda r: r["student_name"]),
    Col("Телефон", lambda r: r["phone"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Поток", lambda r: r["cohort_code"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Организация", lambda r: r["organization"]),
    Col("Должность", lambda r: r["position"]),
    Col("Дата", lambda r: r["employed_at"], "date"),
]


@router.get("/export")
async def export_employment(
    p: View,
    db: DB,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    where = _where(p, q, branch_id, course_id, None, date_from, date_to)
    rows = (await db.execute(_select(where).limit(MAX_ROWS + 1))).all()
    check_cap(rows)
    return await xlsx_response(
        db,
        p,
        entity="employment",
        slug="trudoustroistvo",
        title="Трудоустройство",
        columns=EMPLOYMENT_COLUMNS,
        rows=[_out(r) for r in rows],
        filters={
            "q": q, "branch_id": branch_id, "course_id": course_id,
            "date_from": date_from, "date_to": date_to,
        },
    )  # fmt: skip


async def _check_links(
    db: AsyncSession, student_id: uuid.UUID, enrollment_id: uuid.UUID | None
) -> None:
    graduate = (
        await db.execute(
            select(
                exists().where(Enrollment.student_id == student_id, Enrollment.status == GRADUATE)
            )
        )
    ).scalar_one()
    if not graduate:
        raise DomainError(NOT_GRADUATE)
    if enrollment_id is not None:
        owner = (
            await db.execute(select(Enrollment.student_id).where(Enrollment.id == enrollment_id))
        ).scalar_one_or_none()
        if owner != student_id:
            raise DomainError(EMPLOYMENT_ENROLLMENT_MISMATCH)


def _snapshot(e: Employment) -> dict[str, Any]:
    return {"organization": e.organization, "position": e.position, "employed_at": e.employed_at}


@router.post("", status_code=201)
async def create_employment(body: EmploymentCreate, p: Change, db: DB) -> dict[str, Any]:
    student = (
        await db.execute(select(Student).where(Student.id == body.student_id, *student_filters(p)))
    ).scalar_one_or_none()
    if student is None:
        raise DomainError(NOT_FOUND)
    await _check_links(db, student.id, body.enrollment_id)
    job = Employment(
        student_id=student.id,
        enrollment_id=body.enrollment_id,
        organization=body.organization,
        position=body.position or None,
        employed_at=body.employed_at,
    )
    db.add(job)
    await db.flush()
    await record(
        db, p.id, "employment.create", "employment", job.id,
        {"student": [None, student.full_name], **diff_of({}, _snapshot(job))},
        branch_id=student.branch_id,
    )  # fmt: skip
    return _out(await _one(db, p, job.id))


@router.patch("/{employment_id}")
async def update_employment(
    employment_id: uuid.UUID, body: EmploymentUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    row = await _one(db, p, employment_id)
    job, student = row[0], row[1]

    async def current() -> dict[str, Any]:
        return _out(await _one(db, p, employment_id))

    await check_version(db, job, version, "employment", current)
    before = _snapshot(job)
    sent = body.model_fields_set
    if "enrollment_id" in sent:
        await _check_links(db, student.id, body.enrollment_id)
        job.enrollment_id = body.enrollment_id
    if "organization" in sent and body.organization:
        job.organization = body.organization
    if "position" in sent:
        job.position = body.position or None
    if "employed_at" in sent and body.employed_at:
        job.employed_at = body.employed_at
    await db.flush()
    await record(
        db, p.id, "employment.update", "employment", job.id, diff_of(before, _snapshot(job)),
        branch_id=student.branch_id,
    )  # fmt: skip
    return _out(await _one(db, p, employment_id))


@router.delete("/{employment_id}", status_code=204)
async def delete_employment(employment_id: uuid.UUID, p: Change, db: DB) -> None:
    row = await _one(db, p, employment_id)
    job, student = row[0], row[1]
    snapshot = _snapshot(job)
    await db.delete(job)
    await db.flush()
    await record(
        db, p.id, "employment.delete", "employment", employment_id,
        {"student": [student.full_name, None], **diff_of(snapshot, {})},
        branch_id=student.branch_id,
    )  # fmt: skip
