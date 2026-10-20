"""Instructor cards: cohorts, students, income from own cohorts, payouts, the default rate.

Rights: section `instructors` (view to read, change to write; the instructor role never writes).
The instructor role sees only their own card (any other instructor is 404). Branch scope: a
branch-bound user sees instructors of their branch or of all branches, and only their branch's
cohorts in the numbers. Numbers come from `app.metrics.money`; there is no «efficiency» (#17).
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.education.scope import cohort_filters, is_instructor, writer
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.metrics import cohort_enrolled
from app.metrics.money import cohort_income, instructor_stats
from app.models import AppUser, Branch, Cohort, Course, Role

router = APIRouter(
    prefix="/api/v1/instructors", tags=["instructors"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("instructors", "view")]
Change = Annotated[Principal, writer("instructors")]

Rate = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class RateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_rate: Rate


def _users_where(p: Principal) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = [Role.code == "instructor"]
    if p.branch_id is not None:
        where.append(or_(AppUser.branch_id.is_(None), AppUser.branch_id == p.branch_id))
    if is_instructor(p):
        where.append(AppUser.id == p.id)  # the instructor sees themself only
    return where


def _select(where: list[ColumnElement[bool]]) -> Any:
    return (
        select(AppUser, Branch.name)
        .join(Role, Role.id == AppUser.role_id)
        .outerjoin(Branch, Branch.id == AppUser.branch_id)
        .where(*where)
    )


def _out(u: AppUser, branch: str | None, stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": u.id,
        "version": u.version,
        "full_name": u.full_name,
        "phone": u.phone,
        "branch_id": u.branch_id,
        "branch_name": branch,
        "is_active": u.is_active,
        "default_rate": u.default_rate,
        **stats,
    }


async def _cards(
    db: AsyncSession, p: Principal, q: str | None, limit: int | None = None
) -> list[dict[str, Any]]:
    where = _users_where(p)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(or_(AppUser.full_name.ilike(like), AppUser.phone.ilike(like)))
    query = _select(where).order_by(AppUser.full_name, AppUser.id)
    rows = (await db.execute(query.limit(limit) if limit else query)).all()
    stats = await instructor_stats(db, [u.id for u, _ in rows], cohort_filters(p))
    return [_out(u, b, stats[u.id]) for u, b in rows]


async def _load(db: AsyncSession, p: Principal, user_id: uuid.UUID) -> tuple[AppUser, str | None]:
    row = (await db.execute(_select([*_users_where(p), AppUser.id == user_id]))).first()
    if row is None:
        raise DomainError(NOT_FOUND)  # also another instructor's card, for an instructor
    return row[0], row[1]


async def _detail(db: AsyncSession, p: Principal, u: AppUser, branch: str | None) -> dict[str, Any]:
    stats = (await instructor_stats(db, [u.id], cohort_filters(p)))[u.id]
    cohorts = (
        await db.execute(
            select(Cohort, Course.name)
            .join(Course, Course.id == Cohort.course_id)
            .where(Cohort.instructor_id == u.id, *cohort_filters(p))
            .order_by(Cohort.start_date.desc(), Cohort.code)
        )
    ).all()
    ids = [c.id for c, _ in cohorts]
    enrolled, income = await cohort_enrolled(db, ids), await cohort_income(db, ids)
    return {
        **_out(u, branch, stats),
        "cohorts_list": [
            {
                "id": c.id,
                "code": c.code,
                "course_name": course,
                "status": c.status,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "rate": c.instructor_rate,
                "students": enrolled[c.id],
                "income": income[c.id],
            }
            for c, course in cohorts
        ],
    }


@router.get("")
async def list_instructors(p: View, db: DB, q: str | None = None) -> dict[str, Any]:
    items = await _cards(db, p, q)
    return {"items": items, "total": len(items)}


INSTRUCTOR_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Инструктор", lambda r: r["full_name"]),
    Col("Телефон", lambda r: r["phone"]),
    Col("Филиал", lambda r: r["branch_name"] or "Все"),
    Col("Потоков", lambda r: r["cohorts"], "int"),
    Col("Студентов", lambda r: r["students"], "int"),
    Col("Доход с потоков", lambda r: r["income"], "money"),
    Col("Выплачено", lambda r: r["paid_out"], "money"),
    Col("Ставка по умолчанию", lambda r: r["default_rate"], "money"),
]


@router.get("/export")
async def export_instructors(p: View, db: DB, q: str | None = None) -> Response:
    rows = await _cards(db, p, q, MAX_ROWS + 1)
    check_cap(rows)
    return await xlsx_response(
        db,
        p,
        entity="instructor",
        slug="instruktory",
        title="Инструкторы",
        columns=INSTRUCTOR_COLUMNS,
        rows=rows,
        filters={"q": q},
    )


@router.get("/{user_id}")
async def get_instructor(user_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    u, branch = await _load(db, p, user_id)
    return await _detail(db, p, u, branch)


@router.patch("/{user_id}")
async def update_instructor(
    user_id: uuid.UUID, body: RateUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    u, branch = await _load(db, p, user_id)
    await check_version(db, u, version, "app_user", lambda: _detail(db, p, u, branch))
    before = {"default_rate": str(u.default_rate)}
    u.default_rate = body.default_rate
    await db.flush()
    await db.refresh(u)
    await record(
        db,
        p.id,
        "user.update",
        "app_user",
        u.id,
        diff_of(before, {"default_rate": str(u.default_rate)}),
        branch_id=u.branch_id,
    )
    return await _detail(db, p, u, branch)
