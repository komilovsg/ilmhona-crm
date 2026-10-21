"""Import of a teacher's journal into a cohort's attendance (preview + apply) on an invented file."""

from datetime import date, timedelta
from typing import Any

import httpx

from app.cohorts.status import today
from tests.conftest import SignedIn, make_role, sql
from tests.edu import C, make_cohort, make_course, make_room
from tests.journal_fixture import Student, journal_xlsx
from tests.test_attendance import enroll, mark, past_cohort


def url(cohort: dict[str, Any], step: str) -> str:
    return f"{C}/{cohort['id']}/attendance/import/{step}"


async def send(
    c: httpx.AsyncClient, cohort: dict[str, Any], step: str, data: bytes, **params: Any
) -> httpx.Response:
    return await c.post(
        url(cohort, step),
        content=data,
        params={k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()},
        headers={"Content-Type": "application/octet-stream"},
    )


async def days(c: httpx.AsyncClient, cohort: dict[str, Any]) -> list[date]:
    return [
        date.fromisoformat(le["date"]) for le in (await c.get(f"{C}/{cohort['id']}/lessons")).json()
    ]


def short(ds: list[date]) -> list[str | date]:
    return [f"{d:%d.%m}" for d in ds]


async def marks_in_db() -> dict[tuple[str, str], tuple[bool, str | None]]:
    rows = await sql(
        "SELECT l.lesson_date::text, s.full_name, a.present, a.reason FROM attendance a "
        "JOIN lesson l ON l.id = a.lesson_id JOIN enrollment e ON e.id = a.enrollment_id "
        "JOIN student s ON s.id = e.student_id"
    )
    return {(r[0], r[1]): (r[2], r[3]) for r in rows}


async def audit_import_count() -> int:
    return int(
        (await sql("SELECT count(*) FROM audit_log WHERE action = 'attendance.import'"))[0][0]
    )


# ---- preview ---------------------------------------------------------------------------------


async def test_preview_detects_matches_and_plans_every_cell_and_writes_nothing(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, "Каримов Али")
    await enroll(admin, cohort, "Рахимова Мадина")
    await enroll(admin, cohort, "Юсупов Фарход")  # not in the file
    ds = await days(admin, cohort)
    data = journal_xlsx(
        short(ds[:4]),
        [
            ("Али Каримов", ["б", "н", "у", None], False),  # token order
            ("Madina Rahimova", ["б", "б", "б", "б"], False),  # Latin
            ("Ушедший Студент", ["б", None, None, None], True),  # struck, not in the CRM
        ],
    )
    r = await send(admin, cohort, "preview", data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detected"] == {"sheet": "Журнал", "row": 3, "col": 2, "explicit": False}
    assert [d["status"] for d in body["dates"]] == ["lesson"] * 4
    assert {x["student_name"]: x["tier"] for x in body["rows"]} == {
        "Каримов Али": "translit",
        "Рахимова Мадина": "translit",
    }
    (gone,) = body["unmatched"]
    assert (gone["name"], gone["struck"], gone["marks"]) == ("Ушедший Студент", True, 1)
    assert [m["student_name"] for m in body["missing"]] == ["Юсупов Фарход"]
    assert body["counts"]["add"] == 7 and body["counts"]["unmatched"] == 1
    assert {c["plan"] for c in body["cells"]} == {"add"}
    # nothing was written, nothing audited
    assert await marks_in_db() == {}
    assert await audit_import_count() == 0
    assert (await sql("SELECT count(*) FROM audit_log WHERE action = 'attendance.mark'"))[0][0] == 0


async def test_typed_dates_with_the_wrong_year_and_unknown_marks(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    # Sheets stamped the year the cell was typed in: here one year off
    wrong = [d.replace(year=d.year - 1) if d.month != 2 or d.day != 29 else d for d in ds[:2]]
    data = journal_xlsx(
        list(wrong), [("Каримов Али", ["б", "?"], False)], title=False, numbers=False
    )
    body = (await send(admin, cohort, "preview", data)).json()
    assert [d["date"] for d in body["dates"]] == [d.isoformat() for d in ds[:2]]
    assert body["counts"]["add"] == 1 and body["counts"]["unknown"] == 1


async def test_explicit_sheet_row_and_column(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    data = journal_xlsx(short(ds[:2]), [("Каримов Али", ["б", "н"], False)])
    r = await send(admin, cohort, "preview", data, sheet="Журнал", row=3, col="B")
    assert r.status_code == 200 and r.json()["detected"]["explicit"] is True
    r = await send(admin, cohort, "preview", data, row=1)
    assert (r.status_code, r.json()["code"]) == (422, "journal_no_dates")
    r = await send(admin, cohort, "preview", data, sheet="нет")
    assert (r.status_code, r.json()["code"]) == (422, "validation_failed")


# ---- apply -----------------------------------------------------------------------------------


async def test_apply_writes_marks_with_the_reason_audits_and_is_idempotent(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    data = journal_xlsx(short(ds[:3]), [("Каримов Али", ["б", "н", "у"], False)])
    r = await send(admin, cohort, "apply", data)
    assert r.status_code == 200, r.text
    assert (r.json()["marks_added"], r.json()["lessons_created"]) == (3, 0)
    assert await marks_in_db() == {
        (ds[0].isoformat(), "Каримов Али"): (True, None),
        (ds[1].isoformat(), "Каримов Али"): (False, None),
        (ds[2].isoformat(), "Каримов Али"): (False, "уважительная причина"),
    }
    sentences = [
        e["text"]
        for e in (await admin.get("/api/v1/audit", params={"page_size": 50})).json()["items"]
        if "импорт посещаемости" in e["text"]
    ]
    assert sentences == [
        f"User root: импорт посещаемости {cohort['code']} — 3 отметок, 0 уроков добавлено"
    ]
    # second run: everything is «same», nothing written, nothing audited again
    r = await send(admin, cohort, "apply", data)
    assert (r.json()["marks_added"], r.json()["counts"]["same"]) == (0, 3)
    assert await audit_import_count() == 1
    assert len(await marks_in_db()) == 3
    # the grid sees them
    grid = (await admin.get(f"{C}/{cohort['id']}/attendance")).json()
    assert grid["students"][0]["present"] == 1


async def test_a_different_existing_mark_stays_unless_overwrite(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    assert (await mark(admin, lessons[0], e, present=False, reason="болел")).status_code == 200
    assert (await mark(admin, lessons[1], e, present=True)).status_code == 200
    data = journal_xlsx(short(ds[:3]), [("Каримов Али", ["б", "б", "н"], False)])
    prev = (await send(admin, cohort, "preview", data)).json()
    assert (prev["counts"]["differ"], prev["counts"]["same"], prev["counts"]["add"]) == (1, 1, 1)
    (d,) = prev["differ"]
    assert (d["mark"], d["current"]) == ("б", "отсутствовал (болел)")

    r = await send(admin, cohort, "apply", data)
    assert (r.json()["marks_added"], r.json()["marks_overwritten"]) == (1, 0)
    marks = await marks_in_db()
    assert marks[(ds[0].isoformat(), "Каримов Али")] == (False, "болел")  # kept

    r = await send(admin, cohort, "apply", data, overwrite=True)
    assert (r.json()["marks_added"], r.json()["marks_overwritten"]) == (0, 1)
    marks = await marks_in_db()
    assert marks[(ds[0].isoformat(), "Каримов Али")] == (True, None)
    entries = (await admin.get("/api/v1/audit", params={"page_size": 50})).json()["items"]
    assert any("перезаписано: 1" in e["text"] for e in entries)


async def test_missing_past_lessons_are_created_with_the_cohort_time_and_room(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    await sql(
        "DELETE FROM lesson WHERE cohort_id = :c AND lesson_date IN (:a, :b)",
        c=cohort["id"],
        a=ds[1],
        b=ds[2],
    )
    data = journal_xlsx(short(ds[:4]), [("Каримов Али", ["б", "б", "н", "б"], False)])
    prev = (await send(admin, cohort, "preview", data)).json()
    assert [d["status"] for d in prev["dates"]] == ["lesson", "create", "create", "lesson"]
    assert prev["counts"]["lessons_to_create"] == 2
    assert (await sql("SELECT count(*) FROM lesson WHERE cohort_id = :c", c=cohort["id"]))[0][
        0
    ] == 7

    r = await send(admin, cohort, "apply", data)
    assert (r.json()["marks_added"], r.json()["lessons_created"]) == (4, 2)
    made = await sql(
        "SELECT lesson_date, to_char(starts_at AT TIME ZONE 'Asia/Dushanbe', 'HH24:MI'), "
        "to_char(ends_at AT TIME ZONE 'Asia/Dushanbe', 'HH24:MI'), room_id::text = :r "
        "FROM lesson WHERE cohort_id = :c AND lesson_date IN (:a, :b) ORDER BY 1",
        c=cohort["id"],
        a=ds[1],
        b=ds[2],
        r=cohort["room_id"],
    )
    assert [(m[1], m[2], m[3]) for m in made] == [("10:00", "11:30", True)] * 2
    entries = (await admin.get("/api/v1/audit", params={"page_size": 50})).json()["items"]
    assert any("4 отметок, 2 уроков добавлено" in e["text"] for e in entries)
    # idempotent: no second copy of the lessons
    r = await send(admin, cohort, "apply", data)
    assert (r.json()["marks_added"], r.json()["lessons_created"]) == (0, 0)
    assert (await sql("SELECT count(*) FROM lesson WHERE cohort_id = :c", c=cohort["id"]))[0][
        0
    ] == 9

    # without the option the date is skipped with the reason
    await sql("DELETE FROM attendance")
    await sql(
        "DELETE FROM lesson WHERE id IN (SELECT id FROM lesson WHERE lesson_date = :a)", a=ds[1]
    )
    r = await send(admin, cohort, "apply", data, create_lessons=False)
    assert (r.json()["marks_added"], r.json()["lessons_created"]) == (3, 0)
    assert r.json()["counts"]["skip_no_lesson"] == 1


async def test_future_days_before_enrollment_expelled_and_cancelled_are_skipped(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    new = await enroll(admin, cohort, "Каримов Али")
    gone = await enroll(admin, cohort, "Рахимова Мадина")
    await enroll(admin, cohort, "Юсупов Фарход")
    ds = await days(admin, cohort)
    await sql("UPDATE enrollment SET enrolled_at = :d WHERE id = :i", d=ds[2], i=new)
    assert (
        await admin.patch(f"/api/v1/enrollments/{gone}", json={"status": "отчислен"})
    ).status_code == 200
    assert (await admin.post(f"/api/v1/lessons/{lessons[3]}/cancel")).status_code in (200, 204)
    ahead = today() + timedelta(days=3)
    data = journal_xlsx(
        [*short(ds[:5]), f"{ahead:%d.%m}"],
        [
            ("Каримов Али", ["б", "б", "б", "б", "б", "б"], False),
            ("Рахимова Мадина", ["б", None, None, None, None, "б"], False),
            ("Юсупов Фарход", [None, None, None, None, None, "б"], False),
        ],
    )
    body = (await send(admin, cohort, "preview", data)).json()
    plans = {}
    for c in body["cells"]:
        plans.setdefault(c["plan"], []).append(c)
    assert len(plans["skip_before_enrollment"]) == 2  # Али: the first two days
    assert len(plans["skip_expelled"]) == 1  # Мадина, ds[0]
    assert len(plans["skip_future"]) == 3  # the future column, three students
    assert len(plans["skip_no_lesson"]) == 1  # Али on the cancelled lesson
    assert body["dates"][5]["status"] == "future"
    r = await send(admin, cohort, "apply", data)
    # Али: ds[2], ds[4]; Фарход has only the future mark
    assert r.json()["marks_added"] == 2 and r.json()["lessons_created"] == 0
    assert (await sql("SELECT count(*) FROM lesson WHERE cohort_id = :c", c=cohort["id"]))[0][
        0
    ] == 9


async def test_a_busy_room_skips_the_lesson_with_the_reason(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    await sql(
        "DELETE FROM lesson WHERE cohort_id = :c AND lesson_date IN (:a, :b)",
        c=cohort["id"],
        a=ds[1],
        b=ds[1] + timedelta(days=7),
    )
    # another cohort holds the same room at that time on that day
    other = await make_cohort(
        admin,
        await make_course("Другой"),
        cohort["room_id"],
        start=ds[1],
        weeks=1,
        weekdays=[ds[1].isoweekday()],
    )
    data = journal_xlsx(short(ds[:3]), [("Каримов Али", ["б", "б", "б"], False)])
    prev = (await send(admin, cohort, "preview", data)).json()
    assert prev["dates"][1]["status"] == "conflict"
    assert other["code"] in prev["dates"][1]["reason"]
    r = await send(admin, cohort, "apply", data)
    assert (r.json()["marks_added"], r.json()["lessons_created"]) == (2, 0)
    assert r.json()["skipped_lessons"][0]["status"] == "conflict"


# ---- rights ----------------------------------------------------------------------------------


async def test_rights_and_scope(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    other_ins = await login_as("ins2", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, _ = await past_cohort(admin, instructor_id=me)
    await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)
    data = journal_xlsx(short(ds[:2]), [("Каримов Али", ["б", "н"], False)])

    # an instructor imports into their own cohort, not into somebody else's
    r = await send(other_ins, cohort, "preview", data)
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    r = await send(other_ins, cohort, "apply", data)
    assert r.status_code == 404
    assert (await send(ins, cohort, "apply", data)).status_code == 200
    # another branch's manager
    role = await make_role("Посещаемость", {"attendance": "change"})
    far = await login_as("far", role, branch="Истаравшан")
    assert (await send(far, cohort, "preview", data)).status_code == 404
    # view only, and nobody
    viewer = await login_as("viewer", await make_role("Смотрящий", {"attendance": "view"}))
    for step in ("preview", "apply"):
        r = await send(viewer, cohort, step, data)
        assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    async with httpx.AsyncClient(
        transport=admin._transport, base_url="http://test", headers={"X-Requested-With": "ilm"}
    ) as anon:
        assert (await send(anon, cohort, "preview", data)).status_code == 401


# ---- caps and formula safety -----------------------------------------------------------------


async def test_caps_and_formula_safety(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    e = await enroll(admin, cohort, "Каримов Али")
    ds = await days(admin, cohort)

    big = b"x" * (2 * 1024 * 1024 + 1)
    r = await send(admin, cohort, "preview", big)
    assert (r.status_code, r.json()["code"]) == (413, "import_too_large")
    r = await send(admin, cohort, "preview", b"PK\x03\x04junk")
    assert (r.status_code, r.json()["code"]) == (422, "import_unreadable")
    rows = "\n".join(f"Имя Фамилия{i};б" for i in range(2005))
    r = await send(admin, cohort, "preview", f"ФИО;{ds[0]:%d.%m}\n{rows}".encode())
    assert (r.status_code, r.json()["code"]) == (422, "import_too_many_rows")

    # a formula is never run: as a mark it is an unknown mark, as a name it comes back neutralised
    csv_data = (
        f"ФИО;{ds[0]:%d.%m};{ds[1]:%d.%m}\nКаримов Али;=1+1;б\n=HYPERLINK Evil Link;б;б\n"
    ).encode()
    body = (await send(admin, cohort, "preview", csv_data)).json()
    assert body["counts"]["add"] == 1 and body["counts"]["unknown"] == 1
    assert body["unknown"][0]["mark"] == "'=1+1"
    assert body["unmatched"][0]["name"].startswith("'=")
    # a real formula cell of an xlsx has no cached value: it reads as empty
    from openpyxl import Workbook

    wb = Workbook()
    ws: Any = wb.active
    ws.append(["ФИО", f"{ds[0]:%d.%m}", f"{ds[1]:%d.%m}"])
    ws.append(["Каримов Али", "=SUM(1,2)", "н"])
    from io import BytesIO

    buf = BytesIO()
    wb.save(buf)
    body = (await send(admin, cohort, "preview", buf.getvalue())).json()
    assert body["counts"]["add"] == 1 and body["counts"]["unknown"] == 0
    assert await marks_in_db() == {}
    _ = e
