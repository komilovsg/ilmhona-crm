"""Students: list, create, edit, delete, detail with enrollment history.

Rights: `students` view / change (change never for the instructor role: #24). Branch scope;
an instructor with `students` view sees only students of their own cohorts. The student status
and the counts come from `app.metrics`.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.education.errors import STUDENT_IN_USE
from app.education.scope import branch_for_write, cohort_filters, student_filters, writer
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
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


async def _counts(db: AsyncSession, p: Principal, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Enrollments per student, only in cohorts this user may see (like the history)."""
    if not ids:
        return {}
    rows = await db.execute(
        select(Enrollment.student_id, func.count())
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .where(Enrollment.student_id.in_(ids), *cohort_filters(p))
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


async def _detail(db: AsyncSession, p: Principal, student: Student, branch: str) -> dict[str, Any]:
    """The history lists only cohorts in the user's scope: no other branch's or (instructor)
    other teachers' cohorts."""
    status = (await student_statuses(db, [student.id]))[student.id]
    rows = await db.execute(
        select(Enrollment, Cohort, Course.name)
        .join(Cohort, Cohort.id == Enrollment.cohort_id)
        .join(Course, Course.id == Cohort.course_id)
        .where(Enrollment.student_id == student.id, *cohort_filters(p))
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


def _student_where(
    p: Principal, q: str | None, status: str | None, branch_id: uuid.UUID | None
) -> list[Any]:
    where: list[Any] = list(student_filters(p))
    if branch_id:
        where.append(Student.branch_id == branch_id)
    if status:
        where.append(student_status_expr() == status)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(or_(Student.full_name.ilike(like), Student.phone.ilike(like)))
    return where


def _student_select(where: list[Any]) -> Any:
    return (
        select(Student, Branch.name, student_status_expr())
        .join(Branch, Branch.id == Student.branch_id)
        .where(*where)
        .order_by(Student.full_name, Student.id)
    )


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
    where = _student_where(p, q, status, branch_id)
    total = (await db.execute(select(func.count()).select_from(Student).where(*where))).scalar_one()
    rows = (
        await db.execute(_student_select(where).limit(page_size).offset((page - 1) * page_size))
    ).all()
    counts = await _counts(db, p, [s.id for s, _, _ in rows])
    return {
        "items": [_out(s, b, st, counts.get(s.id, 0)) for s, b, st in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


STUDENT_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("ФИО", lambda s: s["full_name"]),
    Col("Пол", lambda s: {"male": "М", "female": "Ж"}.get(s["gender"] or "")),
    Col("Телефон", lambda s: s["phone"]),
    Col("Филиал", lambda s: s["branch_name"]),
    Col("Статус", lambda s: s["status"]),
    Col("Потоков", lambda s: s["enrollments_count"], "int"),
    Col("Добавлен", lambda s: s["created_at"], "date"),
]


@router.get("/export")
async def export_students(
    p: View,
    db: DB,
    q: str | None = None,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
) -> Response:
    where = _student_where(p, q, status, branch_id)
    rows = (await db.execute(_student_select(where).limit(MAX_ROWS + 1))).all()
    check_cap(rows)
    counts = await _counts(db, p, [s.id for s, _, _ in rows])
    return await xlsx_response(
        db,
        p,
        entity="student",
        slug="studenty",
        title="Студенты",
        columns=STUDENT_COLUMNS,
        rows=[_out(s, b, st, counts.get(s.id, 0)) for s, b, st in rows],
        filters={"q": q, "status": status, "branch_id": branch_id},
    )


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
    return await _detail(db, p, student, (await _load(db, p, student.id))[1])


@router.get("/{student_id}")
async def get_student(student_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    student, branch = await _load(db, p, student_id)
    return await _detail(db, p, student, branch)


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
    return await _detail(db, p, student, branch)


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
