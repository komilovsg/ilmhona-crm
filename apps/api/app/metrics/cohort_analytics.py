"""Cohort analytics (SPEC «Аналитика потока»): how a group is doing, from the one set of metrics.

No money anywhere in here. Targets and the pass score are the cohort's EFFECTIVE grading scheme
(its own, else the academy standard), never constants.

- Weeks are ISO weeks (Mon–Sun) of the lesson's Asia/Dushanbe date. Period filters only the
  attendance numbers: week = the current ISO week, month = the last 4 ISO weeks (current one
  included), course = every held lesson.
- Retention: started = enrollments (any status) enrolled on or before the date of the cohort's
  first held lesson (the start date while nothing was held). Left = expelled + «перестал ходить»
  (a red risk) among them; now = started − left; retention = now / started.
- Attendance of a week / period = present ÷ marked marks of the not expelled students over held
  lessons (unmarked is not an absence); a student's own attendance % is the metrics one
  (present ÷ held since enrollment).
- Grades: projected totals of the not expelled students, buckets 0–49 / 50–69 / 70–84 / 85–100;
  pass rate = projected ≥ pass score among those with a projected total.
- Risk (expelled are never listed; every matching reason is shown):
  red «перестал ходить» = the last 3+ held lessons of the student are all absences (an unmarked
  lesson breaks the run); orange «пропустил 2 урока подряд» = the run is exactly 2; orange
  «посещаемость за 4 недели ниже цели» = over the last 28 days ≥ 3 held lessons and
  present ÷ held < the target; orange «прогноз ниже проходного» = projected < pass score once a
  manual category has a score or the student has ≥ 4 held lessons.
- Top (отличники): attendance ≥ 90 % and projected ≥ 85.
- End of course: only when the cohort is завершён or its last lesson was held.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cohorts import status as st
from app.core import clock
from app.metrics import grading
from app.metrics.attendance import EXPELLED, enrollment_results
from app.models import Attendance, Cohort, Enrollment, Lesson, Student

PERIODS = ("week", "month", "course")
MONTH_WEEKS = 4
STOPPED_RUN = 3
MISSED_RUN = 2
WINDOW_DAYS = 28
WINDOW_MIN_HELD = 3
FORECAST_MIN_HELD = 4
TOP_ATTENDANCE = 90
TOP_PROJECTED = 85
BUCKETS = ((0, 49), (50, 69), (70, 84), (85, 100))
RED = "red"
ORANGE = "orange"
OK = "ok"
BELOW = "below"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def window_start(period: str, today: date) -> date | None:
    """First day of the period's window (None = the whole course)."""
    if period == "week":
        return week_start(today)
    if period == "month":
        return week_start(today) - timedelta(weeks=MONTH_WEEKS - 1)
    return None


def percent(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def status_of(part: int, whole: int, target: int) -> str | None:
    """ok when part/whole reaches the target (integer maths, no float edge); None = no data."""
    if not whole:
        return None
    return OK if 100 * part >= target * whole else BELOW


def trailing_absences(marks: list[bool | None]) -> int:
    """Absences at the end of a student's held lessons (oldest first); None = unmarked."""
    run = 0
    for m in reversed(marks):
        if m is False:
            run += 1
        else:
            break
    return run


def is_top(attendance_percent: float | None, projected: int | None) -> bool:
    return (
        attendance_percent is not None
        and projected is not None
        and attendance_percent >= TOP_ATTENDANCE
        and projected >= TOP_PROJECTED
    )


def risk_reasons(
    *,
    marks: list[bool | None],
    window_present: int,
    window_held: int,
    projected: int | None,
    has_scores: bool,
    held: int,
    scheme: grading.Scheme,
) -> tuple[str | None, list[dict[str, str]]]:
    """(level, reasons) of one student; level None = not at risk."""
    reasons: list[dict[str, str]] = []
    run = trailing_absences(marks)
    if run >= STOPPED_RUN:
        reasons.append({"code": "stopped", "text": f"перестал ходить: {run} урока(ов) подряд"})
    elif run == MISSED_RUN:
        reasons.append({"code": "missed_2", "text": "пропустил 2 урока подряд"})
    if (
        window_held >= WINDOW_MIN_HELD
        and status_of(window_present, window_held, scheme.target_attendance) == BELOW
    ):
        shown = f"{percent(window_present, window_held):g}".replace(".", ",")
        reasons.append(
            {
                "code": "low_attendance",
                "text": f"посещаемость за 4 недели {shown} % (цель {scheme.target_attendance} %)",
            }
        )
    if (
        projected is not None
        and (has_scores or held >= FORECAST_MIN_HELD)
        and projected < scheme.pass_score
    ):
        reasons.append(
            {"code": "forecast", "text": f"прогноз {projected} ниже проходного {scheme.pass_score}"}
        )
    if not reasons:
        return None, reasons
    return (RED if run >= STOPPED_RUN else ORANGE), reasons


@dataclass
class _Student:
    enrollment: Enrollment
    student: Student
    enrolled_on: date
    marks: list[bool | None]  # per held lesson since enrollment, oldest first
    dates: list[date]


def _held(le: Any, now: datetime) -> bool:
    """`held_lesson` of the attendance metrics, on a loaded row."""
    return not le.cancelled and le.starts_at <= now


async def cohort_analytics(
    db: AsyncSession,
    cohort: Cohort,
    period: str,
    *,
    with_phone: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or clock.now()
    today = now.astimezone(st.TZ).date()
    scheme = await grading.scheme_of(db, cohort.id)
    lessons = (
        await db.execute(
            select(Lesson.id, Lesson.lesson_date, Lesson.cancelled, Lesson.starts_at)
            .where(Lesson.cohort_id == cohort.id)
            .order_by(Lesson.starts_at)
        )
    ).all()
    held = [le for le in lessons if _held(le, now)]
    upcoming = [le for le in lessons if not le.cancelled and le.starts_at > now]
    rows = (
        await db.execute(
            select(Enrollment, Student)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.cohort_id == cohort.id)
            .order_by(Student.full_name, Enrollment.id)
        )
    ).all()
    marked: dict[tuple[uuid.UUID, uuid.UUID], bool] = {
        (lesson_id, enrollment_id): present
        for lesson_id, enrollment_id, present in (
            await db.execute(
                select(Attendance.lesson_id, Attendance.enrollment_id, Attendance.present)
                .join(Lesson, Lesson.id == Attendance.lesson_id)
                .where(Lesson.cohort_id == cohort.id)
            )
        ).all()
    }
    results = await enrollment_results(db, cohort.id, now=now)

    students: list[_Student] = []
    for e, s in rows:
        on = e.enrolled_at.astimezone(st.TZ).date()
        mine = [le for le in held if le.lesson_date >= on]
        students.append(
            _Student(
                e,
                s,
                on,
                [marked.get((le.id, e.id)) for le in mine],
                [le.lesson_date for le in mine],
            )
        )
    active = [x for x in students if x.enrollment.status != EXPELLED]

    # ---- risk ------------------------------------------------------------------------------
    cutoff = today - timedelta(days=WINDOW_DAYS - 1)
    manual_keys = {c.key for c in scheme.manual}
    risk: list[dict[str, Any]] = []
    stopped_ids: set[uuid.UUID] = set()
    for x in active:
        res = results[x.enrollment.id]
        in_window = [m for m, d in zip(x.marks, x.dates, strict=True) if d >= cutoff]
        level, reasons = risk_reasons(
            marks=x.marks,
            window_present=sum(1 for m in in_window if m),
            window_held=len(in_window),
            projected=res["projected"],
            has_scores=any(k in manual_keys for k in res["scores"]),
            held=res["held"],
            scheme=scheme,
        )
        if level == RED:
            stopped_ids.add(x.enrollment.id)
        if level:
            item: dict[str, Any] = {
                "enrollment_id": x.enrollment.id,
                "student_id": x.student.id,
                "student_name": x.student.full_name,
                "level": level,
                "reasons": reasons,
                "attendance_percent": res["percent"],
                "projected": res["projected"],
            }
            if with_phone:
                item["phone"] = x.student.phone
            risk.append(item)
    risk.sort(key=lambda r: (r["level"] != RED, -len(r["reasons"]), r["student_name"]))

    # ---- retention -------------------------------------------------------------------------
    first_day = held[0].lesson_date if held else cohort.start_date
    started = [x for x in students if x.enrolled_on <= first_day]
    expelled = [x for x in started if x.enrollment.status == EXPELLED]
    stopped = [x for x in started if x.enrollment.id in stopped_ids]
    now_count = len(started) - len(expelled) - len(stopped)
    retention = {
        "started": len(started),
        "now": now_count,
        "left": {"expelled": len(expelled), "stopped": len(stopped)},
        "percent": percent(now_count, len(started)),
        "target": scheme.target_retention,
        "status": status_of(now_count, len(started), scheme.target_retention),
    }

    # ---- attendance ------------------------------------------------------------------------
    start = window_start(period, today)
    in_period = [le for le in held if start is None or le.lesson_date >= start]
    by_week: dict[date, dict[str, Any]] = {}
    week_of = {le.id: week_start(le.lesson_date) for le in in_period}
    for le in in_period:
        w = by_week.setdefault(week_of[le.id], {"lessons": 0, "present": 0, "marked": 0})
        w["lessons"] += 1
    active_ids = {x.enrollment.id for x in active}
    for (lesson_id, enrollment_id), present in marked.items():
        if lesson_id in week_of and enrollment_id in active_ids:
            w = by_week[week_of[lesson_id]]
            w["marked"] += 1
            w["present"] += 1 if present else 0
    first_week = week_start(start) if start else (min(by_week) if by_week else None)
    weeks: list[dict[str, Any]] = []
    if first_week is not None:
        w0 = first_week
        while w0 <= week_start(today):
            w = by_week.get(w0, {"lessons": 0, "present": 0, "marked": 0})
            weeks.append(
                {
                    "week_start": w0,
                    "week_end": w0 + timedelta(days=6),
                    "lessons": w["lessons"],
                    "present": w["present"],
                    "marked": w["marked"],
                    "percent": percent(w["present"], w["marked"]),
                }
            )
            w0 += timedelta(weeks=1)
    p_present = sum(w["present"] for w in weeks)
    p_marked = sum(w["marked"] for w in weeks)
    attendance = {
        "weeks": weeks,
        "lessons": len(in_period),
        "present": p_present,
        "marked": p_marked,
        "percent": percent(p_present, p_marked),
        "target": scheme.target_attendance,
        "status": status_of(p_present, p_marked, scheme.target_attendance),
    }

    # ---- grades ----------------------------------------------------------------------------
    projected = {x.enrollment.id: results[x.enrollment.id]["projected"] for x in active}
    values = [v for v in projected.values() if v is not None]
    passed = sum(1 for v in values if v >= scheme.pass_score)
    grades = {
        "buckets": [
            {
                "label": f"{lo}–{hi}",
                "from": lo,
                "to": hi,
                "count": sum(1 for v in values if lo <= v <= hi),
            }
            for lo, hi in BUCKETS
        ],
        "students": len(values),
        "no_data": len(projected) - len(values),
        "average": round(sum(values) / len(values), 1) if values else None,
        "pass_score": scheme.pass_score,
        "pass_rate": {
            "passed": passed,
            "of": len(values),
            "percent": percent(passed, len(values)),
            "target": scheme.target_pass_rate,
            "status": status_of(passed, len(values), scheme.target_pass_rate),
        },
    }

    # ---- top -------------------------------------------------------------------------------
    top = sorted(
        (
            {
                "enrollment_id": x.enrollment.id,
                "student_id": x.student.id,
                "student_name": x.student.full_name,
                "attendance_percent": results[x.enrollment.id]["percent"],
                "projected": results[x.enrollment.id]["projected"],
            }
            for x in active
            if is_top(results[x.enrollment.id]["percent"], results[x.enrollment.id]["projected"])
        ),
        key=lambda r: (-r["projected"], -r["attendance_percent"], r["student_name"]),
    )

    # ---- end of course ---------------------------------------------------------------------
    available = cohort.status == st.DONE or (bool(held) and not upcoming)
    final_rows: list[dict[str, Any]] = []
    if available:
        for x in active:
            res = results[x.enrollment.id]
            final_rows.append(
                {
                    "enrollment_id": x.enrollment.id,
                    "student_id": x.student.id,
                    "student_name": x.student.full_name,
                    "points": res["points"],
                    "total": res["total"],
                    "passed": res["passed"],
                    "excellent": is_top(res["percent"], res["total"]),
                    "attendance_percent": res["percent"],
                }
            )
    final = {
        "available": available,
        "categories": [
            {"key": c.key, "name": c.name, "weight": c.weight, "kind": c.kind}
            for c in scheme.categories
        ],
        "pass_score": scheme.pass_score,
        "rows": final_rows,
    }

    return {
        "cohort_id": cohort.id,
        "cohort_code": cohort.code,
        "period": period,
        "window": {"from": start, "to": today},
        "scheme": {
            "source": scheme.source,
            "pass_score": scheme.pass_score,
            "target_retention": scheme.target_retention,
            "target_attendance": scheme.target_attendance,
            "target_pass_rate": scheme.target_pass_rate,
        },
        "thresholds": {"top_attendance": TOP_ATTENDANCE, "top_projected": TOP_PROJECTED},
        "retention": retention,
        "attendance": attendance,
        "grades": grades,
        "risk": risk,
        "top": top,
        "final": final,
    }
