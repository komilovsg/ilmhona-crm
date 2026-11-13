"""The academy goal text (everyone reads it, the superadmin sets it) and goals with automatic
progress (superadmin only). Every number of a goal comes from `app.metrics.goals`.

The superadmin is the user whose role has the code `superadmin` (`Principal.is_superadmin`); other
roles, whatever rights they hold, get 403.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import CurrentUser, Principal, require_csrf_header
from app.core import clock
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, VALIDATION_FAILED, DomainError, errors
from app.core.versioning import Version, check_version
from app.metrics.goals import METRICS, RATE_METRICS, current_value, pace
from app.models import AcademyGoal, AppUser, Branch, Goal, Note

GOAL_DATES_INVALID = errors.define(
    "goal_dates_invalid", 422, "The deadline must be after the start date"
)
errors.on_constraint("goal_dates_order_check", GOAL_DATES_INVALID)
for _check in (
    "goal_title_check",
    "goal_metric_check",
    "goal_target_check",
    "goal_rate_target_check",
    "academy_goal_text_check",
):
    errors.on_constraint(_check, VALIDATION_FAILED)

Metric = Literal[
    "graduates_total",
    "active_students",
    "collection_rate_month",
    "income",
    "new_enrollments",
    "courses_launched",
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
GoalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=280)]
Target = Annotated[Decimal, Field(gt=0, le=Decimal("999999999999.99"), decimal_places=2)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def superadmin_only(p: CurrentUser) -> Principal:
    if not p.is_superadmin:
        raise DomainError(FORBIDDEN, section="dashboard", level="superadmin")
    return p


Superadmin = Annotated[Principal, Depends(superadmin_only)]

academy_router = APIRouter(
    prefix="/api/v1/academy", tags=["goals"], dependencies=[Depends(require_csrf_header)]
)
router = APIRouter(
    prefix="/api/v1/goals", tags=["goals"], dependencies=[Depends(require_csrf_header)]
)


# ---- academy goal ------------------------------------------------------------------------


class AcademyGoalUpdate(Strict):
    text: GoalText


async def _academy_row(db: AsyncSession) -> AcademyGoal:
    return (await db.execute(select(AcademyGoal))).scalar_one()


async def _academy_out(db: AsyncSession) -> dict[str, Any]:
    row = (
        await db.execute(
            select(AcademyGoal, AppUser.full_name).outerjoin(
                AppUser, AppUser.id == AcademyGoal.updated_by
            )
        )
    ).one()
    goal, by = row
    return {
        "text": goal.text,
        "version": goal.version,
        "updated_at": goal.updated_at,
        "updated_by": by,
    }


@academy_router.get("/goal")
async def get_academy_goal(_: CurrentUser, db: DB) -> dict[str, Any]:
    return await _academy_out(db)


@academy_router.patch("/goal")
async def update_academy_goal(
    body: AcademyGoalUpdate, version: Version, p: Superadmin, db: DB
) -> dict[str, Any]:
    row = await _academy_row(db)

    async def current() -> dict[str, Any]:
        return await _academy_out(db)

    await check_version(db, row, version, "academy_goal", current, changes=body.model_dump())
    before = {"text": row.text}
    row.text = body.text
    row.updated_by = p.id
    row.updated_at = clock.now()
    await db.flush()
    await record(
        db, p.id, "academy_goal.update", "academy_goal", row.id, diff_of(before, {"text": row.text})
    )
    return await _academy_out(db)


# ---- goals -------------------------------------------------------------------------------


class GoalCreate(Strict):
    title: Title
    metric: Metric
    target: Target
    start_date: date
    deadline: date
    branch_id: uuid.UUID | None = None


class GoalUpdate(Strict):
    title: Title | None = None
    metric: Metric | None = None
    target: Target | None = None
    start_date: date | None = None
    deadline: date | None = None
    branch_id: uuid.UUID | None = None


def _num(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral() else float(value)


def _snapshot(g: Goal) -> dict[str, Any]:
    return {
        "title": g.title,
        "metric": g.metric,
        "target": _num(g.target),
        "start_date": g.start_date,
        "deadline": g.deadline,
        "branch_id": g.branch_id,
        "archived": g.archived,
    }


def _validate(metric: str, target: Decimal, start: date, deadline: date) -> None:
    if deadline <= start:
        raise DomainError(GOAL_DATES_INVALID)
    if metric in RATE_METRICS and target > 100:
        raise DomainError(VALIDATION_FAILED)


async def _check_branch(db: AsyncSession, branch_id: uuid.UUID | None) -> None:
    if (
        branch_id is not None
        and not (await db.execute(select(Branch.id).where(Branch.id == branch_id))).first()
    ):
        raise DomainError(NOT_FOUND)


async def _out(db: AsyncSession, p: Principal, goals: list[Goal]) -> list[dict[str, Any]]:
    branches = {b: n for b, n in (await db.execute(select(Branch.id, Branch.name))).all()}
    notes = {
        g: n
        for g, n in (
            await db.execute(
                select(Note.goal_id, func.count())
                .where(Note.owner_id == p.id, Note.goal_id.in_([g.id for g in goals]))
                .group_by(Note.goal_id)
            )
        ).all()
    }
    on = clock.today()
    out = []
    for g in goals:
        current = await current_value(db, p, g.metric, g.branch_id, g.start_date, g.deadline)
        out.append(
            {
                "id": g.id,
                "title": g.title,
                "metric": g.metric,
                "metric_label": METRICS[g.metric],
                "target": float(g.target),
                "start_date": g.start_date,
                "deadline": g.deadline,
                "branch_id": g.branch_id,
                "branch_name": branches.get(g.branch_id) if g.branch_id else None,
                "archived": g.archived,
                "version": g.version,
                "created_at": g.created_at,
                "current": current,
                "notes_count": notes.get(g.id, 0),
                **pace(g.metric, current, g.target, g.start_date, g.deadline, on),
            }
        )
    return out


async def _load(db: AsyncSession, goal_id: uuid.UUID) -> Goal:
    goal = (await db.execute(select(Goal).where(Goal.id == goal_id))).scalar_one_or_none()
    if goal is None:
        raise DomainError(NOT_FOUND)
    return goal


async def _detail(db: AsyncSession, p: Principal, goal: Goal) -> dict[str, Any]:
    return (await _out(db, p, [goal]))[0]


@router.get("")
async def list_goals(p: Superadmin, db: DB, archived: bool = False) -> dict[str, Any]:
    goals = (
        (
            await db.execute(
                select(Goal)
                .where(Goal.archived == archived)
                .order_by(Goal.deadline, Goal.title, Goal.id)
            )
        )
        .scalars()
        .all()
    )
    return {"items": await _out(db, p, list(goals))}


@router.post("", status_code=201)
async def create_goal(body: GoalCreate, p: Superadmin, db: DB) -> dict[str, Any]:
    _validate(body.metric, body.target, body.start_date, body.deadline)
    await _check_branch(db, body.branch_id)
    goal = Goal(
        title=body.title,
        metric=body.metric,
        target=body.target,
        start_date=body.start_date,
        deadline=body.deadline,
        branch_id=body.branch_id,
        created_by=p.id,
    )
    db.add(goal)
    await db.flush()
    await record(db, p.id, "goal.create", "goal", goal.id, diff_of({}, _snapshot(goal)))
    return await _detail(db, p, goal)


@router.patch("/{goal_id}")
async def update_goal(
    goal_id: uuid.UUID, body: GoalUpdate, version: Version, p: Superadmin, db: DB
) -> dict[str, Any]:
    goal = await _load(db, goal_id)

    async def current() -> dict[str, Any]:
        return await _detail(db, p, goal)

    await check_version(
        db, goal, version, "goal", current, changes=body.model_dump(exclude_unset=True)
    )
    before = _snapshot(goal)
    sent = body.model_fields_set
    if "title" in sent and body.title:
        goal.title = body.title
    if "metric" in sent and body.metric:
        goal.metric = body.metric
    if "target" in sent and body.target is not None:
        goal.target = body.target
    if "start_date" in sent and body.start_date:
        goal.start_date = body.start_date
    if "deadline" in sent and body.deadline:
        goal.deadline = body.deadline
    if "branch_id" in sent:
        await _check_branch(db, body.branch_id)
        goal.branch_id = body.branch_id
    _validate(goal.metric, goal.target, goal.start_date, goal.deadline)
    goal.updated_at = clock.now()
    await db.flush()
    await record(db, p.id, "goal.update", "goal", goal.id, diff_of(before, _snapshot(goal)))
    return await _detail(db, p, goal)


async def _set_archived(
    goal_id: uuid.UUID, version: int, p: Principal, db: AsyncSession, archived: bool
) -> dict[str, Any]:
    goal = await _load(db, goal_id)

    async def current() -> dict[str, Any]:
        return await _detail(db, p, goal)

    await check_version(db, goal, version, "goal", current, changes={"archived": archived})
    if goal.archived != archived:
        goal.archived = archived
        goal.updated_at = clock.now()
        await db.flush()
        action = "goal.archive" if archived else "goal.unarchive"
        await record(db, p.id, action, "goal", goal.id, {})
    return await _detail(db, p, goal)


@router.post("/{goal_id}/archive")
async def archive_goal(
    goal_id: uuid.UUID, version: Version, p: Superadmin, db: DB
) -> dict[str, Any]:
    return await _set_archived(goal_id, version, p, db, True)


@router.post("/{goal_id}/unarchive")
async def unarchive_goal(
    goal_id: uuid.UUID, version: Version, p: Superadmin, db: DB
) -> dict[str, Any]:
    return await _set_archived(goal_id, version, p, db, False)
