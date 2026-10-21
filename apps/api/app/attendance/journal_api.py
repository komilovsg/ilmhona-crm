"""Import of a teacher's journal into the attendance of one cohort (preview, then apply).

`POST /cohorts/{id}/attendance/import/preview` reads the uploaded file (xlsx or csv, the raw
request body, like the lead import) and answers what an import would do; it writes nothing.
`POST .../import/apply` takes the same file and the same options and does it, in one transaction.
Both build the one `plan`, so what the preview shows is what apply does.

Rules (see `journal.py` for the file itself):
- a date maps to the cohort's live lesson of that day; a past date without a lesson gets one
  (cohort time and room) when `create_lessons` is on, the day lies inside the cohort's dates, it
  has a mark to write and the room is free; otherwise its cells are skipped with the reason;
- a mark is written only on an empty cell (`add`); a different existing mark (`differ`) stays
  unless `overwrite`; an equal one is `same`; future days, days before the student's enrollment
  and expelled students are skipped;
- «б» is present, «н» absent, «у» absent with the reason «уважительная причина»;
- rights: attendance `change` and the cohort in scope (an instructor: their own cohort only).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.attendance import journal as jr
from app.audit.log import record
from app.auth.deps import Principal, require, require_csrf_header
from app.cohorts import status as st
from app.cohorts.schedule import check_room_free, local_dt
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.education.errors import COHORT_CLOSED
from app.education.scope import check_cohort_visible
from app.export import neutralise
from app.leads.errors import IMPORT_TOO_LARGE
from app.metrics.attendance import EXPELLED
from app.models import Attendance, Cohort, Enrollment, Lesson, Student

router = APIRouter(
    prefix="/api/v1", tags=["attendance"], dependencies=[Depends(require_csrf_header)]
)
Change = Annotated[Principal, require("attendance", "change")]

MAX_CELLS = 4000  # cells listed in the preview answer; the counts always cover all of them
MAX_DIFFER = 300


@dataclass(frozen=True)
class Options:
    sheet: str | None = None
    row: int | None = None
    col: str | None = None
    create_lessons: bool = True
    overwrite: bool = False


@dataclass
class DatePlan:
    col: int
    day: date
    status: str  # lesson, create, future, no_lesson, cancelled, duplicate, outside, conflict
    lesson: Lesson | None = None
    reason: str | None = None
    conflict: dict[str, Any] | None = None


@dataclass
class CellPlan:
    line: int
    col: int
    day: date
    enrollment_id: uuid.UUID
    mark: str
    kind: str
    plan: (
        str  # add, same, differ, skip_future, skip_before_enrollment, skip_expelled, skip_no_lesson
    )
    date_plan: DatePlan | None
    current: tuple[bool, str | None] | None = None
    reason: str | None = None


@dataclass
class Plan:
    journal: jr.Journal
    options: Options
    dates: list[DatePlan] = field(default_factory=list)
    cells: list[CellPlan] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[dict[str, Any]] = field(default_factory=list)


async def _cohort(db: AsyncSession, p: Principal, cohort_id: uuid.UUID) -> Cohort:
    cohort = (await db.execute(select(Cohort).where(Cohort.id == cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)
    return cohort


async def _read_body(request: Request) -> bytes:
    """The raw file, capped while it streams in (the limit holds without Content-Length too)."""
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > jr.MAX_BYTES:
        raise DomainError(IMPORT_TOO_LARGE, limit=jr.MAX_BYTES)
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > jr.MAX_BYTES:
            raise DomainError(IMPORT_TOO_LARGE, limit=jr.MAX_BYTES)
    return bytes(data)


def _expected(kind: str) -> tuple[bool, str | None]:
    if kind == jr.PRESENT:
        return True, None
    return False, jr.EXCUSED_REASON if kind == jr.EXCUSED else None


async def build_plan(db: AsyncSession, cohort: Cohort, data: bytes, opts: Options) -> Plan:
    j = await run_in_threadpool(jr.read_journal, data, sheet=opts.sheet, row=opts.row, col=opts.col)
    plan = Plan(j, opts)
    today = st.today()

    enrollments = (
        await db.execute(
            select(Enrollment, Student.full_name)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.cohort_id == cohort.id)
            .order_by(Student.full_name, Enrollment.id)
        )
    ).all()
    by_id = {e.id: (e, name) for e, name in enrollments}
    lessons = (
        (
            await db.execute(
                select(Lesson).where(Lesson.cohort_id == cohort.id).order_by(Lesson.starts_at)
            )
        )
        .scalars()
        .all()
    )
    live: dict[date, list[Lesson]] = {}
    cancelled_days: set[date] = set()
    for le in lessons:
        if le.cancelled:
            cancelled_days.add(le.lesson_date)
        else:
            live.setdefault(le.lesson_date, []).append(le)
    existing: dict[tuple[uuid.UUID, uuid.UUID], tuple[bool, str | None]] = {
        (a.lesson_id, a.enrollment_id): (a.present, a.reason)
        for a in (
            await db.execute(
                select(Attendance).where(Attendance.lesson_id.in_([le.id for le in lessons]))
            )
        ).scalars()
    }

    # dates -> lessons
    seen: dict[date, int] = {}
    date_of: dict[int, DatePlan] = {}
    for col, hdr in j.dates:
        day = jr.resolve_date(hdr, cohort.start_date, cohort.end_date)
        if day is None:
            continue
        k = seen.get(day, 0)
        seen[day] = k + 1
        dp = DatePlan(col, day, "lesson")
        if day > today:
            dp.status = "future"
        elif k < len(live.get(day, [])):
            dp.lesson = live[day][k]
        elif k > 0:
            dp.status, dp.reason = "duplicate", "дата повторяется в журнале"
        elif day in cancelled_days:
            dp.status, dp.reason = "cancelled", "урок отменён"
        elif not opts.create_lessons:
            dp.status, dp.reason = "no_lesson", "урока нет, создание выключено"
        elif not cohort.start_date <= day <= cohort.end_date:
            dp.status, dp.reason = "outside", "вне дат потока"
        else:
            dp.status = "create"
        plan.dates.append(dp)
        date_of[col] = dp

    # names -> enrollments
    jrows = jr.journal_rows(j)
    people = [jr.Person(e.id, name) for e, name in enrollments]
    matches = jr.match_names([r.name for r in jrows], people)
    matched_ids: set[uuid.UUID] = set()
    for r, m in zip(jrows, matches, strict=True):
        shown = neutralise(r.name)
        if m.person is None:
            plan.unmatched.append(
                {
                    "line": r.line,
                    "name": shown,
                    "struck": r.struck,
                    "marks": len(r.marks),
                    "candidates": list(m.candidates),
                }
            )
            continue
        enrollment, name = by_id[m.person.key]
        matched_ids.add(enrollment.id)
        plan.rows.append(
            {
                "line": r.line,
                "name": shown,
                "struck": r.struck,
                "enrollment_id": enrollment.id,
                "student_name": name,
                "status": enrollment.status,
                "tier": m.tier,
            }
        )
        enrolled_on = enrollment.enrolled_at.astimezone(st.TZ).date()
        for col, text in r.marks.items():
            found = date_of.get(col)
            if found is None:
                continue
            dp = found
            kind = jr.mark_kind(text)
            if kind is None:
                plan.unknown.append(
                    {"line": r.line, "date": dp.day, "name": shown, "mark": neutralise(text)}
                )
                continue
            cell = CellPlan(r.line, col, dp.day, enrollment.id, text, kind, "add", dp)
            if dp.status == "future":
                cell.plan = "skip_future"
            elif enrollment.status == EXPELLED:
                cell.plan = "skip_expelled"
            elif dp.status not in ("lesson", "create"):
                cell.plan, cell.reason = "skip_no_lesson", dp.reason
            elif enrolled_on > dp.day:
                cell.plan = "skip_before_enrollment"
            elif dp.lesson is not None and (dp.lesson.id, enrollment.id) in existing:
                cell.current = existing[(dp.lesson.id, enrollment.id)]
                cell.plan = "same" if cell.current[0] == _expected(kind)[0] else "differ"
            plan.cells.append(cell)

    # a lesson is created only for a day that has something to write, and only if the room is free
    for dp in plan.dates:
        if dp.status != "create":
            continue
        cells = [c for c in plan.cells if c.date_plan is dp and c.plan == "add"]
        if not cells:
            dp.status, dp.reason = "no_lesson", "нечего записывать"
            continue
        try:
            await check_room_free(
                db,
                cohort.room_id,
                [(local_dt(dp.day, cohort.start_time), local_dt(dp.day, cohort.end_time))],
            )
        except DomainError as busy:
            dp.status = "conflict"
            dp.conflict = dict(busy.params)
            dp.reason = f"аудитория занята потоком {busy.params.get('cohort')}"
            for c in cells:
                c.plan, c.reason = "skip_no_lesson", dp.reason

    for e, name in enrollments:
        if e.id not in matched_ids:
            plan.missing.append({"enrollment_id": e.id, "student_name": name, "status": e.status})
    return plan


def _counts(plan: Plan) -> dict[str, int]:
    out = {
        k: 0
        for k in (
            "add",
            "same",
            "differ",
            "skip_future",
            "skip_before_enrollment",
            "skip_expelled",
            "skip_no_lesson",
        )
    }
    for c in plan.cells:
        out[c.plan] += 1
    out["unknown"] = len(plan.unknown)
    out["lessons_to_create"] = sum(d.status == "create" for d in plan.dates)
    out["matched"] = len(plan.rows)
    out["unmatched"] = len(plan.unmatched)
    out["missing"] = len(plan.missing)
    return out


def _opts(
    sheet: str | None, row: int | None, col: str | None, create_lessons: bool, overwrite: bool
) -> Options:
    return Options(sheet or None, row, col or None, create_lessons, overwrite)


def _mark_text(current: tuple[bool, str | None] | None) -> str | None:
    if current is None:
        return None
    return (
        "присутствовал" if current[0] else f"отсутствовал{f' ({current[1]})' if current[1] else ''}"
    )


@router.post("/cohorts/{cohort_id}/attendance/import/preview")
async def import_preview(
    cohort_id: uuid.UUID,
    request: Request,
    p: Change,
    db: DB,
    sheet: Annotated[str | None, Query(max_length=100)] = None,
    row: Annotated[int | None, Query(ge=1, le=jr.MAX_ROWS)] = None,
    col: Annotated[str | None, Query(max_length=3)] = None,
    create_lessons: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """What an import would do. Nothing is written."""
    cohort = await _cohort(db, p, cohort_id)
    plan = await build_plan(
        db, cohort, await _read_body(request), _opts(sheet, row, col, create_lessons, overwrite)
    )
    j = plan.journal
    names = {r["enrollment_id"]: r["student_name"] for r in plan.rows}
    differ = [c for c in plan.cells if c.plan == "differ"]
    return {
        "cohort": {"id": cohort.id, "code": cohort.code},
        "file": {"format": j.format, "sheet": j.table.name, "sheets": j.sheets},
        "detected": {
            "sheet": j.table.name,
            "row": j.header_row + 1,
            "col": j.name_col + 1,
            "explicit": j.explicit,
        },
        "options": {"create_lessons": create_lessons, "overwrite": overwrite},
        "limits": {"bytes": jr.MAX_BYTES, "rows": jr.MAX_ROWS},
        "dates": [
            {
                "col": d.col + 1,
                "date": d.day,
                "status": d.status,
                "lesson_id": d.lesson.id if d.lesson else None,
                "reason": d.reason,
                "conflict": d.conflict,
            }
            for d in plan.dates
        ],
        "rows": plan.rows,
        "unmatched": plan.unmatched,
        "missing": plan.missing,
        "unknown": plan.unknown[:MAX_DIFFER],
        "counts": _counts(plan),
        "cells": [
            {
                "line": c.line,
                "col": c.col + 1,
                "date": c.day,
                "enrollment_id": c.enrollment_id,
                "mark": c.mark,
                "kind": c.kind,
                "plan": c.plan,
            }
            for c in plan.cells[:MAX_CELLS]
        ],
        "cells_truncated": len(plan.cells) > MAX_CELLS,
        "differ": [
            {
                "line": c.line,
                "date": c.day,
                "student_name": names[c.enrollment_id],
                "mark": c.mark,
                "current": _mark_text(c.current),
            }
            for c in differ[:MAX_DIFFER]
        ],
    }


@router.post("/cohorts/{cohort_id}/attendance/import/apply")
async def import_apply(
    cohort_id: uuid.UUID,
    request: Request,
    p: Change,
    db: DB,
    sheet: Annotated[str | None, Query(max_length=100)] = None,
    row: Annotated[int | None, Query(ge=1, le=jr.MAX_ROWS)] = None,
    col: Annotated[str | None, Query(max_length=3)] = None,
    create_lessons: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Writes the `add` cells (and the `differ` ones with `overwrite`), creating the missing past
    lessons first. One transaction; a second run finds everything `same` and writes nothing."""
    cohort = await _cohort(db, p, cohort_id)
    plan = await build_plan(
        db, cohort, await _read_body(request), _opts(sheet, row, col, create_lessons, overwrite)
    )
    counts = _counts(plan)

    created = 0
    for dp in plan.dates:
        if dp.status != "create":
            continue
        lesson = Lesson(
            cohort_id=cohort.id,
            room_id=cohort.room_id,
            lesson_date=dp.day,
            starts_at=local_dt(dp.day, cohort.start_time),
            ends_at=local_dt(dp.day, cohort.end_time),
            source="manual",
        )
        db.add(lesson)
        await db.flush()  # room_busy from the database if somebody took the slot meanwhile
        dp.lesson = lesson
        created += 1

    def values(c: CellPlan) -> dict[str, Any]:
        present, reason = _expected(c.kind)
        assert c.date_plan is not None and c.date_plan.lesson is not None
        return {
            "lesson_id": c.date_plan.lesson.id,
            "enrollment_id": c.enrollment_id,
            "present": present,
            "reason": reason,
            "marked_by": p.id,
        }

    added = 0
    adds = [values(c) for c in plan.cells if c.plan == "add"]
    for i in range(0, len(adds), 500):
        done = await db.execute(
            pg_insert(Attendance)
            .values(adds[i : i + 500])
            .on_conflict_do_nothing()
            .returning(Attendance.lesson_id)
        )
        added += len(done.all())
    overwritten = 0
    if overwrite:
        for c in plan.cells:
            if c.plan != "differ":
                continue
            v = values(c)
            await db.execute(
                pg_insert(Attendance)
                .values(**v)
                .on_conflict_do_update(
                    index_elements=[Attendance.lesson_id, Attendance.enrollment_id],
                    set_={"present": v["present"], "reason": v["reason"], "marked_by": p.id},
                )
            )
            overwritten += 1
    if added or created or overwritten:
        diff: dict[str, Any] = {"marks": [0, added], "lessons": [0, created]}
        if overwritten:
            diff["overwritten"] = [0, overwritten]
        await record(
            db,
            p.id,
            "attendance.import",
            "cohort",
            cohort.id,
            diff,
            branch_id=cohort.branch_id,
            label=cohort.code,
        )
    return {
        "marks_added": added,
        "marks_overwritten": overwritten,
        "lessons_created": created,
        "counts": counts,
        "skipped_lessons": [
            {"date": d.day, "status": d.status, "reason": d.reason}
            for d in plan.dates
            if d.status in ("conflict", "outside", "cancelled", "no_lesson", "duplicate")
        ],
    }
