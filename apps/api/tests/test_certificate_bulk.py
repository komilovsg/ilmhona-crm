"""Certificates C5: bulk issue from an Excel list (template, preview, issue, linking, ZIP)."""

import asyncio
import io
import zipfile
from datetime import date, timedelta
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from openpyxl import Workbook, load_workbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import clock
from tests.certs import make_template
from tests.conftest import SERVER_URL, TEST_DB, SignedIn, make_role, sql
from tests.edu import make_student
from tests.test_certificate_registry import REG, fresh_certificate_numbers, pdf_text

_ = fresh_certificate_numbers
BULK = "/api/v1/certificates/bulk"
HEAD = ["ФИО", "Курс/название", "Дата выдачи", "Телефон", "Пол"]


def sheet(*rows: list[Any], head: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(head or HEAD)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


async def post(
    c: httpx.AsyncClient, tail: str, data: bytes, tid: str, name: str = "list.xlsx", **form: str
) -> httpx.Response:
    return await c.post(
        f"{BULK}/{tail}",
        files={"file": (name, data, "application/octet-stream")},
        data={"template_id": tid, **form},
    )


async def count_certs() -> int:
    return int((await sql("SELECT count(*) FROM certificate"))[0][0])


async def test_issuer_lists_templates_without_the_editor_right(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    tid = await make_template()
    issuer = await login_as("iss", await make_role("Выдача", {"certificates": "change"}))
    r = await issuer.get(f"{BULK}/templates")
    assert r.status_code == 200 and [i["id"] for i in r.json()["items"]] == [tid]
    view = await login_as("vw", await make_role("Вид", {"certificates": "view"}))
    assert (await view.get(f"{BULK}/templates")).status_code == 403


async def test_template_has_russian_headers(admin: httpx.AsyncClient) -> None:
    r = await admin.get(f"{BULK}/template")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    assert [c.value for c in ws[1]] == HEAD


async def test_preview_reports_ok_errors_and_duplicates_and_writes_nothing(
    admin: httpx.AsyncClient,
) -> None:
    tid = await make_template()
    tomorrow = clock.today() + timedelta(days=1)
    data = sheet(
        ["Иванов Иван", "Веб", date(2026, 3, 1), None, "м"],
        ["", "Веб", None, None, None],
        ["Петров Пётр", "Веб", "не дата", None, None],
        ["Иванов Иван", "веб", None, None, None],
        ["Сидоров Сидор", "Веб", tomorrow, None, None],
        ["Каримова Мадина", None, "05.04.2026", "12", "x"],
        ["Алиев Али", "Веб", "05.04.2026", "abc", None],
    )
    before = await sql(
        "SELECT (SELECT count(*) FROM audit_log), (SELECT count(*) FROM certificate)"
    )
    r = await post(
        admin,
        "preview",
        data,
        tid,
        branch_id=str((await sql("SELECT id FROM branch LIMIT 1"))[0][0]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_row = {i["row"]: i for i in body["items"]}
    assert body["counts"] == {"ok": 2, "error": 4, "duplicate": 1}
    assert by_row[2]["status"] == "ok"
    assert by_row[3]["reason"] == "Не указано ФИО"
    assert "не распознана" in by_row[4]["reason"]
    assert by_row[5]["status"] == "duplicate" and "Повтор" in by_row[5]["reason"]
    assert by_row[6]["reason"] == "Дата выдачи в будущем"
    assert "Пол" in by_row[7]["reason"]
    assert by_row[8]["status"] == "ok" and by_row[8]["note"]  # phone not recognised: still OK
    assert (
        await sql("SELECT (SELECT count(*) FROM audit_log), (SELECT count(*) FROM certificate)")
        == before
    )


async def test_file_is_checked_before_it_is_read(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    branch = str((await sql("SELECT id FROM branch LIMIT 1"))[0][0])
    for name, data, reason in (
        ("a.xlsx", b"%PDF-1.4 not a sheet", "not_xlsx"),
        ("a.xlsx", b"PK\x03\x04garbage", "not_xlsx"),
        ("a.xlsx", sheet(), "empty"),
        ("a.xlsx", sheet(["x"], head=["Другое"]), "no_name_column"),
        ("a.xlsx", sheet(*[[f"Человек {i}"] for i in range(501)]), "too_many_rows"),
        ("a.xlsx", sheet(["Иванов"]) + b"0" * (2 * 1024 * 1024), "too_large"),
    ):
        r = await post(admin, "preview", data, tid, name, branch_id=branch)
        assert (r.status_code, r.json()["code"]) == (422, "cert_bulk_file"), (reason, r.text)
        assert r.json()["params"]["reason"] == reason
    assert await count_certs() == 0
    r = await post(admin, "preview", sheet(["Иванов"]), tid)  # no branch for a superadmin
    assert (r.status_code, r.json()["code"]) == (422, "cert_branch_required")


async def test_issue_numbers_audits_and_lists_in_the_registry(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    branch = str((await sql("SELECT id FROM branch WHERE name = 'Душанбе'"))[0][0])
    data = sheet(
        ["Иванов Иван", "Веб", "01.03.2026", None, "м"],
        ["Каримова Мадина", "Дизайн", None, None, "ж"],
        ["", None, None, None, None],
        ["Иванов Иван", "Веб", None, None, None],
    )
    r = await post(admin, "issue", data, tid, "Событие.xlsx", branch_id=branch)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["count"] == 2 and [s["status"] for s in body["skipped"]] == ["duplicate"]
    numbers = sorted(i["number"] for i in body["items"])
    assert len(set(numbers)) == 2 and numbers[0].startswith("CERT-")
    reg = (await admin.get(REG, params={"batch_id": body["batch_id"]})).json()
    assert reg["total"] == 2
    row = next(i for i in reg["items"] if i["student_name"] == "Иванов Иван")
    assert (row["course_name"], row["cohort_code"], row["enrollment_id"]) == ("Веб", None, None)
    assert row["branch_id"] == branch and row["status"] == "valid"
    # the PDF comes from the stored snapshot and the pinned template version
    pdf = await admin.get(f"{REG}/{row['id']}/pdf")
    assert pdf.status_code == 200 and "Иванов Иван" in pdf_text(pdf.content)
    assert "1 марта 2026" in pdf_text(pdf.content)
    # one batch entry in Russian, one entry per certificate
    log = (await admin.get("/api/v1/audit", params={"action": "certificate.bulk_issue"})).json()
    assert len(log["items"]) == 1
    sentence = log["items"][0]["text"]
    assert "массовая выдача" in sentence and "выдано 2" in sentence and "Событие.xlsx" in sentence
    assert "пропущено строк: 1" in sentence
    per = (await admin.get("/api/v1/audit", params={"action": "certificate.issue"})).json()
    assert per["total"] == 2 and all("массовая выдача из Excel" in i["text"] for i in per["items"])
    # the same list again: everything is already held, nothing is issued
    r = await post(admin, "issue", data, tid, branch_id=branch)
    assert (r.status_code, r.json()["code"]) == (409, "cert_bulk_empty")
    assert await count_certs() == 2
    # a batch certificate cannot be reissued, but can be revoked
    assert (
        await admin.post(f"{REG}/{row['id']}/reissue", json={"comment": "x"})
    ).status_code == 409
    rv = await admin.post(f"{REG}/{row['id']}/revoke", json={"reason": "ошибка"})
    assert rv.status_code == 200 and rv.json()["status"] == "revoked"
    # the ZIP holds a PDF per certificate
    z = await admin.get(f"{BULK}/{body['batch_id']}/zip")
    assert z.status_code == 200
    assert len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 2


async def test_phone_links_a_student_of_the_branch_only(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    tid = await make_template()
    mine = await make_student("Алиев Али", "Душанбе", phone="+992900000001")
    await make_student("Чужой Человек", "Истаравшан", phone="+992900000002")
    issuer = await login_as(
        "issuer", await make_role("Выдача", {"certificates": "change"}), branch="Душанбе"
    )
    data = sheet(
        ["Алиев Али", "Курс", None, "90 000 00 01", None],
        ["Чужой Человек", "Курс", None, "+992 900 00 00 02", None],
        ["Без Телефона", "Курс", None, None, None],
    )
    prev = (await post(issuer, "preview", data, tid)).json()
    assert [i["linked"] for i in prev["items"]] == [True, False, False] and prev["linked"] == 1
    r = await post(issuer, "issue", data, tid)
    assert r.status_code == 201, r.text
    rows = await sql("SELECT student_id FROM certificate ORDER BY number")
    assert [x[0] for x in rows] == [mine, None, None]
    got = (await issuer.get(REG)).json()["items"]
    assert {i["student_id"] for i in got} == {str(mine), None}
    # a superadmin working for the other branch links that branch's student, not Душанбе's
    other = str((await sql("SELECT id FROM branch WHERE name = 'Истаравшан'"))[0][0])
    prev = (await post(admin, "preview", data, tid, branch_id=other)).json()
    assert [i["linked"] for i in prev["items"]] == [False, True, False]


async def test_rights_and_branch_scope(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    tid = await make_template()
    data = sheet(["Иванов Иван", "Веб", None, None, "м"])
    view = await login_as("view", await make_role("Вид", {"certificates": "view"}))
    none = await login_as("none", await make_role("Без", {"graduates": "change"}))
    for c in (view, none):
        assert (await c.get(f"{BULK}/template")).status_code == 403
        assert (await post(c, "preview", data, tid)).status_code == 403
        assert (await post(c, "issue", data, tid)).status_code == 403
    assert (await sql("SELECT count(*) FROM audit_log WHERE action LIKE 'certificate.%'"))[0][
        0
    ] == 0
    dsh = await login_as(
        "dsh", await make_role("Выдача", {"certificates": "change"}), branch="Душанбе"
    )
    other = str((await sql("SELECT id FROM branch WHERE name = 'Истаравшан'"))[0][0])
    assert (await post(dsh, "issue", data, tid, branch_id=other)).status_code == 404
    assert await count_certs() == 0
    ok = await post(dsh, "issue", data, tid)
    assert ok.status_code == 201
    batch = ok.json()["batch_id"]
    isr = await login_as(
        "isr", await make_role("Вторая", {"certificates": "change"}), branch="Истаравшан"
    )
    assert (await isr.get(f"{BULK}/{batch}/zip")).status_code == 404
    assert (await isr.get(REG)).json()["total"] == 0
    assert (
        await view.get(f"{BULK}/{batch}/zip")
    ).status_code == 200  # view of the right branch-less role


async def test_cells_are_plain_text_and_a_name_that_does_not_fit_is_a_reason(
    admin: httpx.AsyncClient,
) -> None:
    tid = await make_template()
    branch = str((await sql("SELECT id FROM branch LIMIT 1"))[0][0])
    data = sheet(
        ["@Иванов Иван", "-cmd|' /C calc'!A0", None, None, None],
        ["=HYPERLINK(\"http://x\")", "Веб", None, None, None],  # a formula is never evaluated
        ["А" * 151, "Веб", None, None, None],
    )
    r = await post(admin, "issue", data, tid, branch_id=branch)
    body = r.json()
    assert r.status_code == 201 and body["count"] == 1, r.text
    assert [s["row"] for s in body["skipped"]] == [3, 4]
    assert body["skipped"][0]["reason"] == "Не указано ФИО"
    assert "длиннее" in body["skipped"][1]["reason"]
    # the stored text is the cell as text; the registry Excel neutralises it
    x = await admin.get(REG, params={"format": "xlsx"})
    cells = [c.value for c in load_workbook(io.BytesIO(x.content)).worksheets[0]["B"]]
    assert "'@Иванов Иван" in cells


async def test_migration_0028_up_and_down() -> None:
    name = f"{TEST_DB}_mig_bulk"
    url_ = SERVER_URL.set(database=name)
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url_.render_as_string(hide_password=False))
    engine = create_async_engine(url_)

    async def one(query: str) -> Any:
        async with engine.connect() as conn:
            return (await conn.execute(text(query))).scalar_one()

    nullable = (
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'certificate' AND column_name = 'enrollment_id'"
    )
    try:
        await asyncio.to_thread(command.upgrade, cfg, "0027")
        assert await one(nullable) == "NO"
        await asyncio.to_thread(command.upgrade, cfg, "0028")
        assert await one(nullable) == "YES"
        assert (
            await one(
                "SELECT count(*) FROM pg_constraint WHERE conname = 'certificate_source_check'"
            )
            == 1
        )
        await asyncio.to_thread(command.downgrade, cfg, "0027")
        assert await one(nullable) == "NO"
        await asyncio.to_thread(command.upgrade, cfg, "head")
        assert await one(nullable) == "YES"
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()
