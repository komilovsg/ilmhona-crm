"""Excel export: same rows as the list, scope, rights, formula neutralising, audit entry."""

from datetime import date, datetime
from io import BytesIO
from typing import Any

import httpx
from openpyxl import load_workbook

from app.cohorts.status import TZ
from app.export import MAX_ROWS, XLSX, neutralise
from tests.conftest import SignedIn, make_role, sql
from tests.edu import C, instructor_rights, make_cohort, make_course, make_room, make_student

STUDENTS = "/api/v1/students"
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")


def sheet(r: httpx.Response) -> list[tuple[Any, ...]]:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == XLSX
    ws = load_workbook(BytesIO(r.content)).active
    assert ws is not None
    return [tuple(c.value for c in row) for row in ws.iter_rows()]


async def _audit_exports(entity: str) -> list[Any]:
    return await sql(
        "SELECT user_id, diff FROM audit_log WHERE action = 'export' AND entity = :e", e=entity
    )


async def test_students_export_equals_filtered_list(admin: httpx.AsyncClient) -> None:
    for i in range(30):
        await make_student(f"Ali {i:02d}" if i % 2 else f"Bob {i:02d}", phone=f"+9929000000{i:02d}")
    params = {"q": "ali"}
    listed: list[Any] = []
    for page in (1, 2):
        r = await admin.get(STUDENTS, params={**params, "page": page, "page_size": 10})
        listed += r.json()["items"]
    assert len(listed) == 15
    r = await admin.get(f"{STUDENTS}/export", params=params)
    rows = sheet(r)
    assert [row[0] for row in rows[1:]] == [s["full_name"] for s in listed]  # same ids, same order
    assert rows[0][:3] == ("ФИО", "Пол", "Телефон")
    assert r.headers["content-disposition"].startswith('attachment; filename="studenty_')
    assert r.headers["content-disposition"].endswith(f'_{TODAY}.xlsx"')


async def test_typed_cells_frozen_header_width(admin: httpx.AsyncClient) -> None:
    await make_course("Python", 1234)
    r = await admin.get("/api/v1/courses/export")
    ws = load_workbook(BytesIO(r.content)).active
    assert ws is not None
    assert ws.freeze_panes == "A2"
    price = ws["C2"]
    assert price.value == 1234 and "TJS" in price.number_format
    assert ws["D2"].value == 3
    assert (ws.column_dimensions["A"].width or 0) >= 8


async def test_dates_are_dates(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    await make_cohort(admin, course, room)
    ws = load_workbook(BytesIO((await admin.get(f"{C}/export")).content)).active
    assert ws is not None
    assert isinstance(ws["F2"].value, datetime | date)
    assert "yyyy" in ws["F2"].number_format


def test_formula_neutralised() -> None:
    for bad in ("=1+1", "+cmd|' /C calc'!A0", "-2+3", "@SUM(A1)", "\tx", "\rx"):
        assert neutralise(bad) == "'" + bad
    assert neutralise("Иван") == "Иван"
    assert neutralise("+992 900 00 00 01") == "+992 900 00 00 01"


async def test_formula_in_data_is_neutralised_in_file(admin: httpx.AsyncClient) -> None:
    await make_student('=HYPERLINK("http://evil")')
    await make_student("@evil")
    names = [row[0] for row in sheet(await admin.get(f"{STUDENTS}/export"))[1:]]
    assert sorted(names) == sorted(['\'=HYPERLINK("http://evil")', "'@evil"])
    ws = load_workbook(BytesIO((await admin.get(f"{STUDENTS}/export")).content)).active
    assert ws is not None
    assert all(c.data_type != "f" for row in ws.iter_rows() for c in row)


async def test_audit_entry_written(admin: httpx.AsyncClient) -> None:
    await make_student("Ali")
    await make_student("Bob")
    await admin.get(f"{STUDENTS}/export", params={"q": "ali"})
    rows = await _audit_exports("student")
    assert len(rows) == 1
    assert rows[0][1] == {"rows": 1, "filters": {"q": "ali"}}
    assert rows[0][0] is not None


async def test_manager_scope_and_rights(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    await make_student("Dushanbe Kid", "Душанбе")
    await make_student("Istaravshan Kid", "Истаравшан")
    role = await make_role("Просмотр", {"students": "view", "cohorts": "view"})
    mgr = await login_as("mgr", role, branch="Душанбе")
    names = [row[0] for row in sheet(await mgr.get(f"{STUDENTS}/export"))[1:]]
    assert names == ["Dushanbe Kid"]
    # the explicit filter of the other branch cannot widen the scope
    r = await mgr.get(f"{STUDENTS}/export", params={"branch_id": str(await _branch("Истаравшан"))})
    assert sheet(r)[1:] == []
    entry = (await _audit_exports("student"))[-1]
    assert entry[1]["rows"] == 0
    # no right: 403, and nothing is written
    nobody = await login_as("nobody", await make_role("Пусто", {"cohorts": "view"}))
    assert (await nobody.get(f"{STUDENTS}/export")).status_code == 403
    assert (await nobody.get("/api/v1/users/export")).status_code == 403
    assert (await nobody.get("/api/v1/audit/export")).status_code == 403
    assert (await nobody.get("/api/v1/rooms/export")).status_code == 403


async def _branch(name: str) -> Any:
    from tests.conftest import branch_id

    return await branch_id(name)


async def test_instructor_exports_only_own_cohorts(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    course, room = await make_course(), await make_room()
    teacher = await login_as("teach", "instructor", branch="Душанбе")
    me = (await teacher.get("/api/v1/auth/me")).json()["id"]
    mine = await make_cohort(admin, course, room, instructor_id=me)
    other_room = await make_room(name="Other")
    await make_cohort(admin, course, other_room, instructor_id=None, weekdays=[2])
    rows = sheet(await teacher.get(f"{C}/export"))
    assert [r[0] for r in rows[1:]] == [mine["code"]]
    listed = (await teacher.get(C)).json()["items"]
    assert [c["code"] for c in listed] == [mine["code"]]
    # an instructor has no students section by default, and no users/audit
    assert (await teacher.get("/api/v1/users/export")).status_code == 403


async def test_instructor_sees_only_own_students(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    course, room = await make_course(), await make_room()
    teacher = await login_as("teach", "instructor", branch="Душанбе")
    me = (await teacher.get("/api/v1/auth/me")).json()["id"]
    cohort = await make_cohort(admin, course, room, instructor_id=me)
    mine, other = await make_student("Mine"), await make_student("Other")
    await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(mine)})
    assert other
    async with instructor_rights(students="view"):
        rows = sheet(await teacher.get(f"{STUDENTS}/export"))
        assert [r[0] for r in rows[1:]] == ["Mine"]
        r = await teacher.get(f"{C}/{cohort['id']}/enrollments/export")
        assert [x[0] for x in sheet(r)[1:]] == ["Mine"]


async def test_cohort_children_export_equals_list(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    for name in ("Zed", "Amy"):
        s = await make_student(name)
        await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(s)})
    listed = (await admin.get(f"{C}/{cohort['id']}/enrollments")).json()
    rows = sheet(await admin.get(f"{C}/{cohort['id']}/enrollments/export"))
    assert [r[0] for r in rows[1:]] == [e["student_name"] for e in listed] == ["Amy", "Zed"]
    lessons = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()
    rows = sheet(await admin.get(f"{C}/{cohort['id']}/lessons/export"))
    assert [
        r[0].date().isoformat() if isinstance(r[0], datetime) else r[0].isoformat()
        for r in rows[1:]
    ] == [le["date"] for le in lessons]


async def test_every_table_exports(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    await make_cohort(admin, course, room)
    monday = (await admin.get(C)).json()["items"][0]["start_date"]
    for url, params in (
        ("/api/v1/users/export", {}),
        ("/api/v1/roles/export", {}),
        ("/api/v1/audit/export", {}),
        ("/api/v1/rooms/export", {}),
        ("/api/v1/courses/export", {}),
        ("/api/v1/rooms/schedule/export", {"date_from": monday}),
        (f"{C}/export", {}),
        (f"{STUDENTS}/export", {}),
    ):
        r = await admin.get(url, params=params)
        assert len(sheet(r)) >= 1, url
    roles = sheet(await admin.get("/api/v1/roles/export"))
    assert "Студенты" in roles[0] and "Журнал" in roles[0]
    sched = sheet(await admin.get("/api/v1/rooms/schedule/export", params={"date_from": monday}))
    grid = (await admin.get("/api/v1/rooms/schedule", params={"date_from": monday})).json()
    assert len(sched) - 1 == len(grid["lessons"]) > 0


async def test_row_cap(admin: httpx.AsyncClient, monkeypatch: Any) -> None:
    import app.export as export_module

    monkeypatch.setattr(export_module, "MAX_ROWS", 2)
    for i in range(3):
        await make_student(f"S{i}")
    r = await admin.get(f"{STUDENTS}/export")
    assert r.status_code == 422 and r.json()["code"] == "export_too_large"
    assert MAX_ROWS == 50_000


async def test_rooms_list_agrees_with_ui_for_instructor(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    teacher = await login_as("teach", "instructor", branch="Душанбе")
    assert (await teacher.get("/api/v1/rooms")).status_code == 403
    assert (await teacher.get("/api/v1/courses")).status_code == 403
    assert (await admin.get("/api/v1/rooms")).status_code == 200
    mgr = await login_as("mgr", "manager", branch="Душанбе")
    assert (await mgr.get("/api/v1/rooms")).status_code == 200


async def test_export_reads_as_a_sentence_in_the_audit(admin: httpx.AsyncClient) -> None:
    await make_student("Ali")
    await admin.get(f"{STUDENTS}/export", params={"q": "ali"})
    items = (await admin.get("/api/v1/audit", params={"action": "export"})).json()["items"]
    assert [i["text"] for i in items] == [
        "User root — выгрузка в Excel: студенты, 1 строка (фильтры: поиск ali)"
    ]
