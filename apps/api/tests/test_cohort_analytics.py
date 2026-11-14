"""Cohort analytics: every number against an independent computation on a seeded fixture,
the effective scheme's targets, rights, no money, the Excel file."""

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction
from io import BytesIO
from math import floor
from typing import Any

import httpx
from openpyxl import load_workbook

from app.cohorts.status import today
from app.metrics import cohort_analytics as ca
from tests.conftest import SignedIn, make_role, sql
from tests.edu import C, make_cohort, make_course, make_room
from tests.test_attendance import enroll, past_cohort

CANCELLED_IDX = 8
LAST_HELD_IDX = 7

# Marks by lesson (oldest first, 9 lessons, the last one cancelled): P present, A absent,
# - not marked. Marks on the cancelled lesson must be ignored.
PATTERNS = {
    "N1": "PPPPPPPPP",
    "N2": "PPPPPPP-A",
    "A": "PPPPPAAAA",
    "B": "PPPPPPAAP",
    "C": "PPPPPAA-A",
    "F": "-----AAAA",  # enrolled 4 days ago: lessons 5, 6, 7 are his
    "G": "AAAAAAAAA",  # expelled
}
SCORES = {"N1": {"homework": 40, "final": 40}, "N2": {"homework": 35, "final": 35}}
LATE = {"F": 4}


async def mark_sql(lesson: str, enrollment: str, value: str) -> None:
    if value == "-":
        return
    await sql(
        "INSERT INTO attendance (lesson_id, enrollment_id, present) VALUES (:l, :e, :p)",
        l=lesson,
        e=enrollment,
        p=value == "P",
    )


async def seed(admin: httpx.AsyncClient, **extra: Any) -> tuple[dict[str, Any], dict[str, str]]:
    cohort, lessons = await past_cohort(admin, **extra)
    ids: dict[str, str] = {}
    for name, pattern in PATTERNS.items():
        e = await enroll(admin, cohort, name)
        ids[name] = e
        for lesson, value in zip(lessons, pattern, strict=True):
            await mark_sql(lesson, e, value)
        for key, points in SCORES.get(name, {}).items():
            await sql(
                "INSERT INTO grade_score (enrollment_id, category_key, points) VALUES (:e, :k, :p)",
                e=e,
                k=key,
                p=points,
            )
    for name, days in LATE.items():
        await sql(
            "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
            d=today() - timedelta(days=days),
            i=ids[name],
        )
    await sql("UPDATE enrollment SET status = 'отчислен' WHERE id = :i", i=ids["G"])
    await sql("UPDATE lesson SET cancelled = true WHERE id = :i", i=lessons[CANCELLED_IDX])
    return cohort, ids


def half_up(x: Fraction) -> int:
    return floor(x + Fraction(1, 2))


def ref_reasons(name: str, *, target: int = 80, pass_score: int = 70) -> set[str]:
    """The risk reasons of a student, computed from the pattern string alone."""
    pattern = PATTERNS[name]
    first = 9 - LATE[name] if name in LATE else 0
    held = pattern[first : LAST_HELD_IDX + 1]
    present = held.count("P")
    reasons = set()
    run = len(re.search(r"A*$", held).group())  # type: ignore[union-attr]
    if run >= 3:
        reasons.add("stopped")
    elif run == 2:
        reasons.add("missed_2")
    if len(held) >= 3 and 100 * present < target * len(held):
        reasons.add("low_attendance")
    scores = SCORES.get(name, {})
    counted = 20 * (1 if held else 0) + 40 * len(scores)
    total = half_up(Fraction(20 * present, len(held))) + sum(scores.values())
    if (
        counted
        and (scores or len(held) >= 4)
        and half_up(Fraction(100 * total, counted)) < pass_score
    ):
        reasons.add("forecast")
    return reasons


async def data(
    c: httpx.AsyncClient, cohort: dict[str, Any], period: str = "course"
) -> dict[str, Any]:
    r = await c.get(f"{C}/{cohort['id']}/analytics", params={"period": period})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def risk_by_name(d: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["student_name"]: r for r in d["risk"]}


async def test_risk_reasons_match_an_independent_computation(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    risk = risk_by_name(await data(admin, cohort))
    for name in PATTERNS:
        expected = ref_reasons(name)
        if name == "G":  # expelled: never listed
            assert name not in risk
        elif expected:
            assert {x["code"] for x in risk[name]["reasons"]} == expected, name
        else:
            assert name not in risk, name
    # the hand-checked cases behind the reference
    assert ref_reasons("A") == {"stopped", "low_attendance", "forecast"}
    assert ref_reasons("B") == {
        "missed_2",
        "low_attendance",
    }  # cancelled lesson 9 does not break it
    assert "stopped" not in ref_reasons("C") and "missed_2" not in ref_reasons("C")  # unmarked
    assert ref_reasons("F") == {"stopped", "low_attendance"}  # 3 lessons since enrollment
    assert ref_reasons("N1") == ref_reasons("N2") == set()
    assert risk["A"]["level"] == "red" and risk["F"]["level"] == "red"
    assert risk["B"]["level"] == risk["C"]["level"] == "orange"


async def test_risk_is_sorted_red_first_and_texts_are_russian(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    risk = (await data(admin, cohort))["risk"]
    levels = [r["level"] for r in risk]
    assert levels == sorted(levels, key=lambda lv: lv != "red")
    assert levels[0] == "red"
    a = next(r for r in risk if r["student_name"] == "A")
    assert a["reasons"][0]["text"] == "перестал ходить: 3 урока(ов) подряд"
    assert "посещаемость за 4 недели 62.5 % (цель 80 %)" in [x["text"] for x in a["reasons"]]
    b = next(r for r in risk if r["student_name"] == "B")
    assert b["reasons"][0] == {"code": "missed_2", "text": "пропустил 2 урока подряд"}


async def test_retention_counts_started_expelled_and_stopped(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    d = await data(admin, cohort)
    # started: everybody enrolled by the first held lesson (not the late F); G expelled, A stopped
    assert d["retention"] == {
        "started": 6,
        "now": 4,
        "left": {"expelled": 1, "stopped": 1},
        "percent": 66.7,
        "target": 85,
        "status": "below",
    }


async def test_targets_come_from_the_effective_scheme_and_an_override_changes_status(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await seed(admin)
    d = await data(admin, cohort)
    assert d["scheme"]["source"] == "standard"
    assert (d["retention"]["target"], d["attendance"]["target"]) == (85, 80)
    assert d["grades"]["pass_rate"]["target"] == 70
    assert d["retention"]["status"] == "below" and d["attendance"]["status"] == "below"
    r = await admin.patch(
        f"{C}/{cohort['id']}/grading",
        json={
            "target_retention": 60,
            "target_attendance": 50,
            "target_pass_rate": 10,
            "pass_score": 40,
        },
    )
    assert r.status_code == 200, r.text
    d = await data(admin, cohort)
    assert d["scheme"]["source"] == "cohort"
    assert (d["retention"]["target"], d["attendance"]["target"]) == (60, 50)
    assert (d["retention"]["status"], d["attendance"]["status"]) == ("ok", "ok")
    assert (d["grades"]["pass_rate"]["target"], d["grades"]["pass_score"]) == (10, 40)
    assert d["grades"]["pass_rate"]["status"] == "ok"
    # the risk rules follow the same scheme: 62.5 % is above a 50 % target, forecast 65 above 40
    risk = risk_by_name(d)
    assert {x["code"] for x in risk["A"]["reasons"]} == ref_reasons("A", target=50, pass_score=40)
    assert "C" not in risk


async def test_weekly_attendance_equals_sql(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    rows = await sql(
        "SELECT date_trunc('week', l.lesson_date)::date, "
        "count(*) FILTER (WHERE a.present), count(*), count(DISTINCT l.id) "
        "FROM attendance a JOIN lesson l ON l.id = a.lesson_id "
        "JOIN enrollment e ON e.id = a.enrollment_id "
        "WHERE l.cohort_id = :c AND NOT l.cancelled AND e.status <> 'отчислен' GROUP BY 1",
        c=cohort["id"],
    )
    expected = {r[0]: (r[1], r[2]) for r in rows}
    d = await data(admin, cohort)
    got = {
        w["week_start"]: (w["present"], w["marked"])
        for w in d["attendance"]["weeks"]
        if w["marked"]
    }
    assert got == {k.isoformat(): v for k, v in expected.items()}
    for w in d["attendance"]["weeks"]:
        monday = date.fromisoformat(w["week_start"])
        assert monday.weekday() == 0 and w["week_end"] == (monday + timedelta(days=6)).isoformat()
        assert w["percent"] == (round(100 * w["present"] / w["marked"], 1) if w["marked"] else None)
    present = sum(v[0] for v in expected.values())
    marked = sum(v[1] for v in expected.values())
    assert d["attendance"]["percent"] == round(100 * present / marked, 1)
    assert (d["attendance"]["present"], d["attendance"]["marked"]) == (present, marked)


async def test_period_window_filters_attendance_only(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    monday = today() - timedelta(days=today().weekday())
    for period, since in (
        ("week", monday),
        ("month", monday - timedelta(weeks=3)),
        ("course", None),
    ):
        d = await data(admin, cohort, period)
        rows = await sql(
            "SELECT count(*) FILTER (WHERE a.present), count(*) FROM attendance a "
            "JOIN lesson l ON l.id = a.lesson_id JOIN enrollment e ON e.id = a.enrollment_id "
            "WHERE l.cohort_id = :c AND NOT l.cancelled AND e.status <> 'отчислен' "
            "AND (CAST(:s AS date) IS NULL OR l.lesson_date >= :s)",
            c=cohort["id"],
            s=since,
        )
        assert (d["attendance"]["present"], d["attendance"]["marked"]) == tuple(rows[0]), period
        # retention and risk are always «now»
        assert d["retention"]["now"] == 4 and len(d["risk"]) == 4
    week = await data(admin, cohort, "week")
    assert [w["week_start"] for w in week["attendance"]["weeks"]] == [monday.isoformat()]
    month = await data(admin, cohort, "month")
    assert len(month["attendance"]["weeks"]) == 4


def test_week_boundaries_are_monday_to_sunday() -> None:
    sunday, monday = date(2026, 11, 15), date(2026, 11, 16)
    assert ca.week_start(sunday) == date(2026, 11, 9)
    assert ca.week_start(monday) == monday
    assert ca.window_start("week", sunday) == date(2026, 11, 9)
    assert ca.window_start("month", monday) == date(2026, 10, 26)
    assert ca.window_start("course", monday) is None


async def test_sunday_and_monday_lessons_fall_in_different_iso_weeks(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Недельный")
    sunday = today() - timedelta(days=80)
    sunday -= timedelta(days=(sunday.weekday() + 1) % 7)
    assert sunday.weekday() == 6
    for lesson, day in ((lessons[0], sunday), (lessons[1], sunday + timedelta(days=1))):
        starts = datetime(day.year, day.month, day.day, 5, tzinfo=UTC)  # 10:00 in Dushanbe
        await sql(
            "UPDATE lesson SET lesson_date = :d, starts_at = :s, ends_at = :e WHERE id = :i",
            d=day,
            s=starts,
            e=starts + timedelta(hours=1),
            i=lesson,
        )
        await mark_sql(lesson, e, "P")
        await sql(
            "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
            d=starts - timedelta(days=1),
            i=e,
        )
    weeks = [w for w in (await data(admin, cohort))["attendance"]["weeks"] if w["marked"]]
    assert [w["week_start"] for w in weeks][:2] == [
        (sunday - timedelta(days=6)).isoformat(),
        (sunday + timedelta(days=1)).isoformat(),
    ]
    assert [(w["lessons"], w["marked"]) for w in weeks][:2] == [(1, 1), (1, 1)]


async def test_grade_distribution_and_pass_rate(admin: httpx.AsyncClient) -> None:
    cohort, ids = await seed(admin)
    d = (await data(admin, cohort))["grades"]
    rows = await sql(
        "SELECT e.id FROM enrollment e WHERE e.cohort_id = :c AND e.status <> 'отчислен'",
        c=cohort["id"],
    )
    assert len(rows) == 6
    grid = (await admin.get(f"{C}/{cohort['id']}/grades")).json()["rows"]
    projected = [r["projected"] for r in grid if r["projected"] is not None]
    for bucket in d["buckets"]:
        assert bucket["count"] == sum(1 for v in projected if bucket["from"] <= v <= bucket["to"])
    assert [b["label"] for b in d["buckets"]] == ["0–49", "50–69", "70–84", "85–100"]
    assert d["students"] == len(projected) and d["no_data"] == len(grid) - len(projected)
    assert d["average"] == round(sum(projected) / len(projected), 1)
    passed = sum(1 for v in projected if v >= 70)
    assert d["pass_rate"]["passed"] == passed and d["pass_rate"]["of"] == len(projected)
    assert d["pass_rate"]["percent"] == round(100 * passed / len(projected), 1)
    assert d["pass_rate"]["status"] == ("ok" if 100 * passed >= 70 * len(projected) else "below")


async def test_top_students_need_90_attendance_and_85_projected(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    top = (await data(admin, cohort))["top"]
    assert [t["student_name"] for t in top] == ["N1"]
    assert (top[0]["attendance_percent"], top[0]["projected"]) == (100.0, 100)


async def test_no_marks_no_forecast_risk_before_four_lessons(admin: httpx.AsyncClient) -> None:
    cohort = await make_cohort(admin, await make_course(), await make_room())
    await enroll(admin, cohort, "Новый")
    d = await data(admin, cohort)
    assert d["risk"] == [] and d["top"] == []
    assert d["retention"]["started"] == 1 and d["attendance"]["percent"] is None
    assert d["attendance"]["status"] is None and d["grades"]["average"] is None
    assert d["final"]["available"] is False and d["final"]["rows"] == []


async def test_end_of_course_table_rows_and_excel(admin: httpx.AsyncClient) -> None:
    cohort, _ = await seed(admin)
    d = await data(admin, cohort)
    final = d["final"]
    assert final["available"] is True  # the last held lesson was yesterday, none ahead
    by_name = {r["student_name"]: r for r in final["rows"]}
    assert set(by_name) == {"N1", "N2", "A", "B", "C", "F"}  # expelled G is out
    assert by_name["N1"]["excellent"] is True and by_name["N1"]["total"] == 100
    assert by_name["N1"]["passed"] is True and by_name["A"]["passed"] is False
    assert by_name["N2"]["excellent"] is False  # 87.5 % attendance
    assert by_name["N1"]["points"] == {"attendance": 20, "homework": 40, "final": 40}

    before = (await sql("SELECT count(*) FROM audit_log WHERE action = 'export'"))[0][0]
    r = await admin.get(f"{C}/{cohort['id']}/analytics/export")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith(
        f'attachment; filename="analitika_{cohort["code"]}_'
    )
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["Итоги курса", "В зоне риска", "Отличники"]
    table = [tuple(c.value for c in row) for row in wb["Итоги курса"].iter_rows()]
    assert table[0] == (
        "Студент",
        "Посещаемость (из 20)",
        "Домашние задания (из 40)",
        "Финал (из 40)",
        "Итого",
        "Зачёт (от 70)",
        "Отличник",
    )
    assert len(table) - 1 == len(final["rows"])
    exported = {row[0]: row for row in table[1:]}
    for name, row in by_name.items():
        assert exported[name][4] == row["total"]
        assert exported[name][5] == ("Да" if row["passed"] else "Нет")
        assert exported[name][6] == ("Да" if row["excellent"] else "Нет")
    assert len(list(wb["В зоне риска"].iter_rows())) - 1 == len(d["risk"])
    assert len(list(wb["Отличники"].iter_rows())) - 1 == len(d["top"])
    entries = await sql(
        "SELECT diff FROM audit_log WHERE action = 'export' AND entity = 'cohort_analytics'"
    )
    assert (
        len(entries) == 1
        and (await sql("SELECT count(*) FROM audit_log WHERE action = 'export'"))[0][0]
        == before + 1
    )
    assert entries[0][0]["rows"] == len(final["rows"]) + len(d["risk"]) + len(d["top"])
    texts = (await admin.get("/api/v1/audit", params={"action": "export"})).json()["items"]
    assert any("аналитика потока" in i["text"] for i in texts)


async def test_end_of_course_not_available_while_lessons_are_ahead(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    await enroll(admin, cohort, "Алиев")
    await sql(
        "UPDATE lesson SET starts_at = now() + interval '2 days', ends_at = now() + interval '2 days 1 hour', "
        "lesson_date = (CURRENT_DATE + 2) WHERE id = :i",
        i=lessons[-1],
    )
    assert (await data(admin, cohort))["final"]["available"] is False
    r = await admin.get(f"{C}/{cohort['id']}/analytics/export")
    assert load_workbook(BytesIO(r.content)).sheetnames == ["В зоне риска", "Отличники"]


async def test_no_money_anywhere_in_the_payload(admin: httpx.AsyncClient) -> None:
    cohort, ids = await seed(admin)
    await sql(
        "INSERT INTO payment (enrollment_id, month_no, amount, method, paid_at, "
        "idempotency_key) VALUES (:e, 1, 500, 'наличные', now(), gen_random_uuid())",
        e=ids["A"],
    )
    text = json.dumps(await data(admin, cohort), ensure_ascii=False).lower()
    for word in (
        "price",
        "amount",
        "payment",
        "debt",
        "paid",
        "money",
        "tjs",
        "долг",
        "оплат",
        "цена",
    ):
        assert word not in text, word


async def test_phones_only_for_those_who_see_the_cohort_students(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, ids = await seed(admin, instructor_id=me)
    await sql("UPDATE student SET phone = '+992900000001' WHERE full_name = 'A'")
    mine = risk_by_name(await data(ins, cohort))
    assert (
        mine["A"]["phone"] == "+992900000001"
    )  # the instructor sees phones of their cohort anyway
    grader = await login_as("gr", await make_role("Оценщик", {"attendance": "view"}))
    seen = risk_by_name(await data(grader, cohort))
    assert "phone" not in seen["A"]
    sheet = load_workbook(
        BytesIO((await grader.get(f"{C}/{cohort['id']}/analytics/export")).content)
    )
    header = [c.value for c in next(sheet["В зоне риска"].iter_rows())]
    assert "Телефон" not in header
    del ids


async def test_permissions_and_scope(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    other = await login_as("ins2", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, _ = await seed(admin, instructor_id=me)
    url = f"{C}/{cohort['id']}/analytics"
    assert (await ins.get(url)).status_code == 200
    assert (await ins.get(f"{url}/export")).status_code == 200
    for path in (url, f"{url}/export"):
        r = await other.get(path)
        assert (r.status_code, r.json()["code"]) == (404, "not_found")
    mgr = await login_as("mgr", "manager", branch="Душанбе")
    assert (await mgr.get(url)).status_code == 200
    away = await login_as("away", "manager", branch="Истаравшан")
    for path in (url, f"{url}/export"):
        assert (await away.get(path)).status_code == 404
    nobody = await login_as("nb", await make_role("Без оценок", {"cohorts": "view"}))
    for path in (url, f"{url}/export"):
        r = await nobody.get(path)
        assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    assert (await admin.get(f"{C}/{uuid.uuid4()}/analytics")).status_code == 404
    assert (await admin.get(url, params={"period": "year"})).status_code == 422
    assert (await ins.get(url)).json()["cohort_id"] == cohort["id"]
