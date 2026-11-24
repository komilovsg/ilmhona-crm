"""Cohort status (#20) and the enrollment cascade (#11): the one code path.

набор before start, активный from start on. A cohort never finishes by date: after end_date it
stays активный and shows «Срок вышел» (`is_overdue`) until someone finishes it by hand
(`finish`). «отменён» is set by hand and sticky; «завершён» is left alone by `sync_status`. Every
write of a cohort and the daily job (`python -m app.cli daily`) call `sync_status`. Finishing
closes the активный enrollments as выпускник (total ≥ the pass score of the cohort's grading
scheme) or завершил, remembering what they were so `reopen` restores them exactly. A scheme
change of a finished cohort flips nothing by itself: `graduation_changes` previews,
`apply_graduation` applies.
"""

import uuid
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.core import clock
from app.metrics import enrollment_results, has_marks
from app.models import Cohort, Enrollment, Lesson, Room, Student

TZ = ZoneInfo("Asia/Dushanbe")

RECRUITING = "набор"
ACTIVE = "активный"
DONE = "завершён"
CANCELLED = "отменён"
GRADUATE = "выпускник"
COMPLETED = "завершил"
STATUSES = (RECRUITING, ACTIVE, DONE, CANCELLED)


def today() -> date:
    return clock.today()


def status_for(start: date, end: date, on: date) -> str:
    """The status of a cohort loaded from history (importer, demo): done after its end."""
    if on < start:
        return RECRUITING
    if on <= end:
        return ACTIVE
    return DONE


def open_status(start: date, on: date) -> str:
    """The automatic part: набор until the start date, активный from then on."""
    return RECRUITING if on < start else ACTIVE


def is_overdue(cohort: Cohort, on: date | None = None) -> bool:
    """«Срок вышел»: still активный after the end date."""
    return cohort.status == ACTIVE and cohort.end_date < (on or today())


async def sync_status(
    db: AsyncSession, cohort: Cohort, actor_id: object, on: date | None = None
) -> bool:
    """набор → активный by the start date (and back if the start moved). Cancelled and finished
    cohorts stay as they are. True when the status changed; the caller audits the cohort."""
    if cohort.status not in (RECRUITING, ACTIVE):
        return False
    new = open_status(cohort.start_date, on or today())
    changed = new != cohort.status
    cohort.status = new
    return changed


async def close_enrollments(db: AsyncSession, cohorts: list[Cohort], actor_id: object) -> None:
    """#11 + grades: an active enrollment closes as выпускник when its total is at least 70,
    otherwise as завершил. A manager may still correct a status by hand afterwards. Any number of
    cohorts at once: two queries in all (the import closes ~100 cohorts in one go)."""
    ids = [c.id for c in cohorts]
    active: dict[object, list[Enrollment]] = {}
    for e in (
        (
            await db.execute(
                select(Enrollment).where(Enrollment.cohort_id.in_(ids), Enrollment.status == ACTIVE)
            )
        )
        .scalars()
        .all()
    ):
        active.setdefault(e.cohort_id, []).append(e)
    if not active:
        return
    results = await enrollment_results(
        db, None, enrollment_ids=[e.id for rows in active.values() for e in rows]
    )
    closed: list[tuple[Cohort, int, int]] = []
    for cohort in cohorts:
        graduates = 0
        for enrollment in active.get(cohort.id, []):
            graduated = results[enrollment.id]["passed"]
            enrollment.status_before_finish = ACTIVE
            enrollment.status = GRADUATE if graduated else COMPLETED
            graduates += graduated
        if cohort.id in active:
            closed.append((cohort, len(active[cohort.id]), graduates))
    await db.flush()
    for cohort, count, graduates in closed:
        await record(
            db,
            actor_id,  # type: ignore[arg-type]
            "cohort.close_enrollments",
            "cohort",
            cohort.id,
            {"enrollments_completed": [0, count], "graduates": [0, graduates]},
            branch_id=cohort.branch_id,
            label=cohort.code,
        )


async def finish_preview(db: AsyncSession, cohort: Cohort, *, lock: bool = False) -> dict[str, Any]:
    """Who the manual finish would close, by the same pass rule as `close_enrollments` (the
    totals come from `enrollment_results`). `graduates` / `completed`: the активный enrollments
    that become выпускник / завершил; `excluded`: everybody else (expelled, set by hand).
    `lock` takes row locks on the enrollments, for `finish`."""
    query = (
        select(Enrollment, Student.full_name)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.cohort_id == cohort.id)
        .order_by(Student.full_name, Enrollment.id)
    )
    if lock:
        query = query.with_for_update(of=Enrollment)
    rows = (await db.execute(query)).all()
    active = [e.id for e, _ in rows if e.status == ACTIVE]
    results = await enrollment_results(db, None, enrollment_ids=active) if active else {}
    out: dict[str, list[dict[str, Any]]] = {"graduates": [], "completed": [], "excluded": []}
    for e, name in rows:
        item = {"enrollment_id": e.id, "student_id": e.student_id, "student_name": name}
        if e.status != ACTIVE:
            out["excluded"].append({**item, "status": e.status})
        elif results[e.id]["passed"]:
            out["graduates"].append(item)
        else:
            out["completed"].append(item)
    return {
        "cohort_id": cohort.id,
        "code": cohort.code,
        "overdue": is_overdue(cohort),
        "lessons_to_free": await _count_ahead(db, cohort),
        **{k: len(v) for k, v in out.items() if k != "excluded"},
        "excluded_count": len(out["excluded"]),
        "lists": out,
    }


def _ahead(cohort: Cohort, on: date) -> list[Any]:
    """The lessons a finish frees: after the finish date, not cancelled, nobody marked."""
    return [
        Lesson.cohort_id == cohort.id,
        ~Lesson.cancelled,
        Lesson.lesson_date > on,
        ~has_marks(),
    ]


async def _count_ahead(db: AsyncSession, cohort: Cohort) -> int:
    return int(
        await db.scalar(select(func.count()).select_from(Lesson).where(*_ahead(cohort, today())))
        or 0
    )


async def release_lessons(db: AsyncSession, cohort: Cohort, on: date | None = None) -> int:
    """Cancel the lessons ahead (see `_ahead`) so the room and the instructor are free again;
    they are flagged `cancelled_by_finish` for `reopen`. Returns how many."""
    result = await db.execute(
        update(Lesson)
        .where(*_ahead(cohort, on or today()))
        .values(cancelled=True, cancelled_by_finish=True)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def finish(
    db: AsyncSession,
    cohort: Cohort,
    actor_id: object,
    preview: dict[str, Any],
    *,
    auto_days: int | None = None,
) -> None:
    """Close the cohort and its активный enrollments as `preview` (taken under the row locks)
    says: remember each one's status, then выпускник / завершил; free the lessons ahead. The
    nightly job passes `auto_days` (the idle days that closed the cohort) for its audit entry."""
    lists = preview["lists"]
    graduates = {i["enrollment_id"] for i in lists["graduates"]}
    ids = graduates | {i["enrollment_id"] for i in lists["completed"]}
    cohort.status = DONE
    if ids:
        for e in (await db.execute(select(Enrollment).where(Enrollment.id.in_(ids)))).scalars():
            e.status_before_finish = e.status
            e.status = GRADUATE if e.id in graduates else COMPLETED
    freed = await release_lessons(db, cohort)
    await db.flush()
    diff: dict[str, Any] = {
        "status": [ACTIVE, DONE],
        "graduates": [0, len(graduates)],
        "completed": [0, len(ids) - len(graduates)],
        "lessons_cancelled": [0, freed],
    }
    if auto_days is not None:
        diff["idle_days"] = [None, auto_days]
    await record(
        db,
        actor_id,  # type: ignore[arg-type]
        "cohort.finish" if auto_days is None else "cohort.auto_close",
        "cohort",
        cohort.id,
        diff,
        branch_id=cohort.branch_id,
        label=cohort.code,
    )


async def auto_close_stale(db: AsyncSession, on: date | None = None) -> int:
    """The nightly job: close every активный cohort with no attendance marks for `stale_days`
    (`app.metrics.stale`) by the same finish as the manual one. Returns how many it closed; a
    second run finds nothing left."""
    from app.metrics.stale import due_clause, due_cohorts

    on = on or today()
    days, due = await due_cohorts(db, on)
    closed = 0
    for found in due:
        # re-read under a row lock: a cohort finished or marked meanwhile is left alone
        cohort = (
            await db.execute(
                select(Cohort).where(Cohort.id == found.id, due_clause(days, on)).with_for_update()
            )
        ).scalar_one_or_none()
        if cohort is None:
            continue
        await finish(db, cohort, None, await finish_preview(db, cohort, lock=True), auto_days=days)
        closed += 1
    return closed


async def has_certificates(db: AsyncSession, cohort: Cohort) -> bool:
    return bool(
        await db.scalar(
            select(Enrollment.id)
            .where(Enrollment.cohort_id == cohort.id, Enrollment.certificate_no.is_not(None))
            .limit(1)
        )
    )


async def reopen(
    db: AsyncSession, cohort: Cohort, actor_id: object
) -> tuple[int, list[dict[str, Any]]]:
    """Back to активный; every enrollment finish closed gets its old status, every lesson it
    cancelled comes back. Returns (statuses restored, lessons that stay cancelled): a slot taken
    meanwhile by another cohort keeps its lesson cancelled, the reopen itself still succeeds."""
    cohort.status = ACTIVE
    restored = 0
    for e in (
        (
            await db.execute(
                select(Enrollment)
                .where(
                    Enrollment.cohort_id == cohort.id, Enrollment.status_before_finish.is_not(None)
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    ):
        e.status = e.status_before_finish  # type: ignore[assignment]
        e.status_before_finish = None
        restored += 1
    back, busy = 0, []
    rows = (
        await db.execute(
            select(Lesson, Room.name)
            .join(Room, Room.id == Lesson.room_id)
            .where(Lesson.cohort_id == cohort.id, Lesson.cancelled_by_finish)
            .order_by(Lesson.starts_at)
            .with_for_update(of=Lesson)
        )
    ).all()
    await db.flush()
    for lesson, room in rows:
        try:
            async with db.begin_nested():
                lesson.cancelled = False
                lesson.cancelled_by_finish = False
                await db.flush()
            back += 1
        except IntegrityError:  # the room or the instructor is taken at that time now
            await db.refresh(lesson)
            lesson.cancelled_by_finish = False  # an ordinary cancelled lesson from now on
            busy.append(
                {
                    "lesson_id": lesson.id,
                    "date": lesson.lesson_date,
                    "start": lesson.starts_at.astimezone(TZ).strftime("%H:%M"),
                    "end": lesson.ends_at.astimezone(TZ).strftime("%H:%M"),
                    "room_name": room,
                    "reason": "аудитория занята",
                }
            )
    await db.flush()
    diff: dict[str, Any] = {"status": [DONE, ACTIVE], "restored": [0, restored]}
    if back or busy:
        diff["lessons_restored"] = [0, back]
    if busy:
        diff["lessons_busy"] = [0, len(busy)]
    await record(
        db,
        actor_id,  # type: ignore[arg-type]
        "cohort.reopen",
        "cohort",
        cohort.id,
        diff,
        branch_id=cohort.branch_id,
        label=cohort.code,
    )
    return restored, busy


async def reevaluate(
    db: AsyncSession,
    enrollment: Enrollment,
    cohort: Cohort,
    actor_id: object,
    results: dict[uuid.UUID, dict[str, Any]] | None = None,
) -> bool:
    """A grade changed on a finished cohort: the closed enrollment follows the new total
    (выпускник at ≥ 70, else завершил), unless a manager set the status by hand
    (`status_manual`) or a certificate was already issued. True when the status changed."""
    if (
        cohort.status != DONE
        or enrollment.status_manual
        or enrollment.status not in (GRADUATE, COMPLETED)
    ):
        return False
    if results is None:  # the import passes the results of all its enrollments at once
        results = await enrollment_results(db, cohort.id, enrollment_ids=[enrollment.id])
    result = results[enrollment.id]
    new = GRADUATE if result["passed"] else COMPLETED
    if new == enrollment.status or (enrollment.certificate_no and new != GRADUATE):
        return False
    before, enrollment.status = enrollment.status, new
    await db.flush()
    await record(
        db,
        actor_id,  # type: ignore[arg-type]
        "enrollment.update",
        "enrollment",
        enrollment.id,
        {"status": [before, new], "reason": [None, "пересчёт по оценкам"]},
        branch_id=cohort.branch_id,
    )
    return True


RECALC_REASON = "пересчёт по шкале оценок"


async def graduation_changes(
    db: AsyncSession, cohort: Cohort
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A finished cohort after its scheme changed: who would become a graduate / stop being
    one by the current totals (`changes`), and who is left as is (`skipped`, with the reason):
    a status set by hand, an issued certificate, an old-system total. Nothing is written: a
    scheme change never flips a status by itself, `apply_graduation` does it on request."""
    if cohort.status != DONE:
        return [], []
    rows = (
        await db.execute(
            select(Enrollment, Student.full_name)
            .join(Student, Student.id == Enrollment.student_id)
            .where(
                Enrollment.cohort_id == cohort.id,
                Enrollment.status.in_((GRADUATE, COMPLETED)),
            )
            .order_by(Student.full_name, Enrollment.id)
        )
    ).all()
    if not rows:
        return [], []
    results = await enrollment_results(db, cohort.id, enrollment_ids=[e.id for e, _ in rows])
    changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for e, name in rows:
        res = results[e.id]
        new = GRADUATE if res["passed"] else COMPLETED
        if new == e.status:
            continue
        item = {
            "enrollment_id": e.id,
            "student_name": name,
            "status": e.status,
            "new_status": new,
            "total": res["total"],
        }
        if e.status_manual:
            skipped.append({**item, "reason": "статус задан вручную"})
        elif e.certificate_no and new != GRADUATE:
            skipped.append({**item, "reason": "выдан сертификат"})
        elif res["legacy"]:
            skipped.append({**item, "reason": "итог из старой системы"})
        else:
            changes.append(item)
    return changes, skipped


async def apply_graduation(
    db: AsyncSession, cohort: Cohort, actor_id: object
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply `graduation_changes`, one audit entry per student."""
    changes, skipped = await graduation_changes(db, cohort)
    if not changes:
        return changes, skipped
    found = {
        e.id: e
        for e in (
            await db.execute(
                select(Enrollment)
                .where(Enrollment.id.in_([c["enrollment_id"] for c in changes]))
                .with_for_update()
            )
        )
        .scalars()
        .all()
    }
    for c in changes:
        found[c["enrollment_id"]].status = c["new_status"]
    await db.flush()
    for c in changes:
        await record(
            db,
            actor_id,  # type: ignore[arg-type]
            "enrollment.update",
            "enrollment",
            c["enrollment_id"],
            {"status": [c["status"], c["new_status"]], "reason": [None, RECALC_REASON]},
            branch_id=cohort.branch_id,
        )
    return changes, skipped
