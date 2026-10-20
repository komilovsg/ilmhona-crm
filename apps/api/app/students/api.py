"""Students: list, create, edit, delete, detail with enrollment history.

Rights: `students` view / change (change never for the instructor role: #24). Branch scope;
an instructor with `students` view sees only students of their own cohorts. The student status
and the counts come from `app.metrics`.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.education.errors import STUDENT_IN_USE
from app.education.scope import branch_for_write, student_filters, writer
from app.metrics import student_status_expr, student_statuses
from app.models import Branch, Cohort, Course, Enrollment, Student

router = APIRouter(
    prefix="/api/v1/students", tags=["students"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("students", "view")]
Change = Annotated[Principal, writer("students")]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
Gender = Annotated[str, StringConstraints(pattern=r"^(male|female)$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StudentCreate(Strict):
    full_name: Name
    gender: Gender | None = None
    phone: Phone | None = None
    branch_id: uuid.UUID | None = None


class StudentUpdate(Strict):
    """Only the fields present change (`phone: null` clears the phone)."""

    full_name: Name | None = None
    gender: Gender | None = None
    phone: Phone | None = None


def _out(s: Student, branch: str, status: str, enrollments: int) -> dict[str, Any]:
    return {
        "id": s.id,
        "full_name": s.full_name,
        "gender": s.gender,
        "phone": s.phone,
        "branch_id": s.branch_id,
        "branch_name": branch,
        "status": status,
        "enrollments_count": enrollments,
        "created_at": s.created_at,
    }


def _snapshot(s: Student) -> dict[str, Any]:
    return {"full_name": s.full_name, "gender": s.gender, "phone": s.phone}


async def _counts(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = await db.execute(
        select(Enrollment.student_id, func.count())
        .where(Enrollment.student_id.in_(ids))
        .group_by(Enrollment.student_id)
    )
    return dict(rows.all())


async def _load(db: AsyncSession, p: Principal, student_id: uuid.UUID) -> tuple[Student, str]:
    row = (
        await db.execute(
            select(Student, Branch.name)
            .join(Branch, Branch.id == Student.branch_id)
            .where(Student.id == student_id, *student_filters(p))
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    return row[0], row[1]


async def _detail(db: AsyncSession, student: Student, branch: str) -> dict[str, Any]:
    status = (await student_statuses(db, [student.id]))[student.id]
    rows = await db.execute(
        select(Enrollment, Cohort, Course.name)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .join(Course, Course.id == Cohort.course_id)
        .where(Enrollment.student_id == student.id)
        .order_by(Enrollment.enrolled_at.desc())
    )
    history = [
        {
            "id": e.id,
            "cohort_id": c.id,
            "cohort_code": c.code,
            "course_name": course,
            "cohort_status": c.status,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "status": e.status,
            "enrolled_at": e.enrolled_at,
        }
        for e, c, course in rows.all()
    ]
    return {**_out(student, branch, status, len(history)), "enrollments": history}


@router.get("")
async def list_students(
    p: View,
    db: DB,
    q: str | None = None,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    where = student_filters(p)
    status_expr = student_status_expr()
    if branch_id:
        where.append(Student.branch_id == branch_id)
    if status:
        where.append(status_expr == status)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(or_(Student.full_name.ilike(like), Student.phone.ilike(like)))
    total = (await db.execute(select(func.count()).select_from(Student).where(*where))).scalar_one()
    rows = (
        await db.execute(
            select(Student, Branch.name, status_expr)
            .join(Branch, Branch.id == Student.branch_id)
            .where(*where)
            .order_by(Student.full_name, Student.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    counts = await _counts(db, [s.id for s, _, _ in rows])
    return {
        "items": [_out(s, b, st, counts.get(s.id, 0)) for s, b, st in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_student(body: StudentCreate, p: Change, db: DB) -> dict[str, Any]:
    student = Student(
        full_name=body.full_name,
        gender=body.gender,
        phone=body.phone or None,
        branch_id=branch_for_write(p, body.branch_id),
    )
    db.add(student)
    await db.flush()
    await record(
        db,
        p.id,
        "student.create",
        "student",
        student.id,
        diff_of({}, _snapshot(student)),
        branch_id=student.branch_id,
    )
    return await _detail(db, student, (await _load(db, p, student.id))[1])


@router.get("/{student_id}")
async def get_student(student_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    student, branch = await _load(db, p, student_id)
    return await _detail(db, student, branch)


@router.patch("/{student_id}")
async def update_student(
    student_id: uuid.UUID, body: StudentUpdate, p: Change, db: DB
) -> dict[str, Any]:
    student, branch = await _load(db, p, student_id)
    before = _snapshot(student)
    sent = body.model_fields_set
    if "full_name" in sent and body.full_name:
        student.full_name = body.full_name
    if "gender" in sent:
        student.gender = body.gender
    if "phone" in sent:
        student.phone = body.phone or None
    await db.flush()
    await record(
        db,
        p.id,
        "student.update",
        "student",
        student.id,
        diff_of(before, _snapshot(student)),
        branch_id=student.branch_id,
    )
    return await _detail(db, student, branch)


@router.delete("/{student_id}", status_code=204)
async def delete_student(student_id: uuid.UUID, p: Change, db: DB) -> None:
    student, _ = await _load(db, p, student_id)
    snapshot, branch_id = _snapshot(student), student.branch_id
    try:
        async with db.begin_nested():
            await db.delete(student)
            await db.flush()
    except IntegrityError as exc:
        raise DomainError(STUDENT_IN_USE) from exc
    await record(
        db,
        p.id,
        "student.delete",
        "student",
        student_id,
        diff_of(snapshot, {}),
        branch_id=branch_id,
    )
