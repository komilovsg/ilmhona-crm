"""Certificates C2: issue (batch, single), reissue, revoke, the registry, the PDF from the stored
snapshot, the verify address and the non-graduate switch."""

import asyncio
import io
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.certificates.issuing import CODE_ALPHABET
from tests.certs import make_template, text_layer, with_layers
from tests.conftest import SERVER_URL, TEST_DB, SignedIn, make_role, sql
from tests.reports import G, finished_cohort

SETTINGS = "/api/v1/cert-settings"
REG = "/api/v1/certificates"


@pytest.fixture(autouse=True)
async def fresh_certificate_numbers() -> Any:
    yield
    await sql("ALTER SEQUENCE certificate_no_seq RESTART")


def pdf_text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


async def graduates(
    admin: httpx.AsyncClient, n: int = 3, **kw: Any
) -> tuple[dict[str, Any], dict[str, str]]:
    cohort, ids = await finished_cohort(
        admin, {f"Студент{i:02d} Имя": (40, 35) for i in range(n)}, **kw
    )
    await sql("UPDATE student SET gender = 'male'")
    return cohort, ids


async def mixed(admin: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    """One graduate and one student who finished without passing."""
    cohort, ids = await finished_cohort(admin, {"Студент00 Имя": (40, 35), "Слабый Иван": (5, 5)})
    await sql("UPDATE student SET gender = 'male'")
    return cohort, ids


def url(cohort: dict[str, Any], tail: str) -> str:
    return f"/api/v1/cohorts/{cohort['id']}/certificates/{tail}"


async def issue(
    admin: httpx.AsyncClient, cohort: dict[str, Any], tid: str, ids: list[str], **extra: Any
) -> httpx.Response:
    return await admin.post(
        url(cohort, "issue"), json={"template_id": tid, "enrollment_ids": ids, **extra}
    )


async def set_settings(admin: httpx.AsyncClient, **body: Any) -> httpx.Response:
    return await admin.patch(SETTINGS, json=body)


# ---- check and batch issue -------------------------------------------------------------------


async def test_check_then_batch_issue_of_twenty_graduates(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 20)
    r = await admin.get(url(cohort, "check"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["template_id"] == tid and body["counts"] == {"ready": 20, "issued": 0, "fix": 0}
    assert all(i["status"] == "ready" and i["score"] == 75 for i in body["items"])
    r = await issue(admin, cohort, tid, list(ids.values()))
    assert r.status_code == 201, r.text
    items = r.json()["items"]
    numbers = sorted(i["number"] for i in items)
    assert len(items) == 20 and len(set(numbers)) == 20
    assert numbers[0].endswith("-0001") and numbers[-1].endswith("-0020")
    assert all(
        len(i["verify_code"]) == 12 and set(i["verify_code"]) <= set(CODE_ALPHABET) for i in items
    )
    assert len({i["verify_code"] for i in items}) == 20
    # the number is the enrollment's number: the graduates list shows the same
    rows = (await sql("SELECT count(*) FROM enrollment WHERE certificate_no IS NOT NULL"))[0][0]
    assert rows == 20
    body = (await admin.get(url(cohort, "check"))).json()
    assert body["counts"] == {"ready": 0, "issued": 20, "fix": 0}
    assert all(i["certificate_id"] and i["number"] for i in body["items"])
    log = (await admin.get("/api/v1/audit", params={"action": "certificate.issue"})).json()
    assert log["total"] == 20 and "выдан сертификат CERT-" in log["items"][0]["text"]


async def test_one_bad_row_fails_the_whole_batch(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 3)
    bad = ids["Студент01 Имя"]
    await sql(
        "UPDATE student SET gender = NULL WHERE id = (SELECT student_id FROM enrollment WHERE id = :i)",
        i=bad,
    )
    # the default template needs a gender only when it has a gender run
    tid = await make_template(
        "gendered",
        with_layers(text_layer("g", {"gender": {"male": "прошёл", "female": "прошла"}})),
    )
    r = await issue(admin, cohort, tid, list(ids.values()))
    assert r.status_code == 422 and r.json()["code"] == "cert_not_ready"
    items = r.json()["params"]["items"]
    assert [(i["enrollment_id"], i["reason"]) for i in items] == [(bad, "no_gender")]
    assert items[0]["text"]
    assert (await sql("SELECT count(*) FROM certificate"))[0][0] == 0
    assert (await sql("SELECT count(*) FROM enrollment WHERE certificate_no IS NOT NULL"))[0][
        0
    ] == 0
    body = (await admin.get(url(cohort, "check"), params={"template_id": tid})).json()
    assert body["counts"] == {"ready": 2, "issued": 0, "fix": 1}


async def test_overflow_missing_signature_and_non_graduate_are_reasons(
    admin: httpx.AsyncClient,
) -> None:
    tid = await make_template(
        "tight",
        with_layers(
            {**text_layer("name", size_pt=60, align="left"), "w_mm": 30, "h_mm": 12},
            {
                "id": "sig", "type": "image", "x_mm": 10, "y_mm": 10, "w_mm": 30, "h_mm": 10,
                "source": {"signature": "instructor"},
            },
        ),
    )  # fmt: skip
    cohort, ids = await mixed(admin)
    other = ids["Слабый Иван"]
    items = {
        i["student_name"]: i
        for i in (await admin.get(url(cohort, "check"), params={"template_id": tid})).json()[
            "items"
        ]
    }
    assert items["Слабый Иван"]["reason"] == "not_graduate"
    assert items["Студент00 Имя"]["reason"] == "missing_signature"
    r = await issue(admin, cohort, tid, [other])
    assert r.status_code == 422 and r.json()["params"]["items"][0]["reason"] == "not_graduate"


async def test_two_concurrent_batches_never_duplicate_a_number(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 6)
    everyone = list(ids.values())
    a, b = await asyncio.gather(
        issue(admin, cohort, tid, everyone), issue(admin, cohort, tid, list(reversed(everyone)))
    )
    assert sorted((a.status_code, b.status_code)) == [201, 409]
    lost = a if a.status_code == 409 else b
    assert lost.json()["code"] == "cert_already_issued"
    numbers = [r[0] for r in await sql("SELECT number FROM certificate")]
    assert len(numbers) == 6 and len(set(numbers)) == 6
    assert (await sql("SELECT count(DISTINCT enrollment_id) FROM certificate"))[0][0] == 6
    # the second try is a 409 as well
    again = await issue(admin, cohort, tid, everyone[:1])
    assert again.status_code == 409


async def test_ids_of_another_cohort_are_404(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, _ = await graduates(admin, 1)
    other, other_ids = await finished_cohort(admin, {"Чужой Один": (40, 35)}, name="O")
    r = await issue(admin, cohort, tid, list(other_ids.values()))
    assert r.status_code == 404


# ---- single issue and the non-graduate switch ------------------------------------------------


async def test_single_issue_and_the_comment(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    _, ids = await graduates(admin, 1)
    eid = ids["Студент00 Имя"]
    r = await admin.post(
        f"/api/v1/enrollments/{eid}/certificate", json={"template_id": tid, "comment": "по просьбе"}
    )
    assert r.status_code == 201, r.text
    cert = r.json()
    assert cert["number"].startswith("CERT-") and cert["student_name"] == "Студент00 Имя"
    got = (await admin.get(f"{REG}/{cert['id']}")).json()
    assert got["comment"] == "по просьбе" and got["status"] == "valid"
    assert (await admin.post(f"/api/v1/enrollments/{eid}/certificate", json={})).status_code == 409
    # the graduates screen numbering is the same number
    assert (await sql("SELECT certificate_no FROM enrollment WHERE id = :i", i=eid))[0][0] == cert[
        "number"
    ]


async def test_a_number_given_by_the_graduates_screen_is_kept(admin: httpx.AsyncClient) -> None:
    await make_template()
    _, ids = await graduates(admin, 1)
    eid = ids["Студент00 Имя"]
    r = await admin.post(f"{G}/{eid}/certificate")
    number = r.json()["certificate_no"]
    r = await admin.post(f"/api/v1/enrollments/{eid}/certificate", json={})
    assert r.status_code == 201 and r.json()["number"] == number
    # the legacy PDF now renders the issued certificate
    pdf = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert pdf.status_code == 200 and number in pdf_text(pdf.content)


async def test_non_graduate_follows_the_setting_and_needs_a_comment(
    admin: httpx.AsyncClient,
) -> None:
    await make_template()
    _, ids = await mixed(admin)
    eid = ids["Слабый Иван"]
    path = f"/api/v1/enrollments/{eid}/certificate"
    r = await admin.post(path, json={"comment": "договорённость"})
    assert (r.status_code, r.json()["code"]) == (409, "not_graduate")
    assert (await set_settings(admin, allow_non_graduate=True)).status_code == 200
    r = await admin.post(path, json={})
    assert (r.status_code, r.json()["code"]) == (422, "cert_comment_required")
    r = await admin.post(path, json={"comment": "   "})
    assert r.status_code == 422
    r = await admin.post(path, json={"comment": "договорённость"})
    assert r.status_code == 201, r.text
    assert r.json()["number"].startswith("CERT-")
    log = (await admin.get("/api/v1/audit", params={"action": "certificate.issue"})).json()
    assert (
        "не выпускнику" in log["items"][0]["text"] and "договорённость" in log["items"][0]["text"]
    )
    # the number stays on the enrollment, flagged as a non-graduate one
    assert (await sql("SELECT certificate_non_graduate FROM enrollment WHERE id = :i", i=eid))[0][0]


# ---- reissue and revoke ----------------------------------------------------------------------


async def test_reissue_keeps_the_number_and_replaces_the_old_row(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 1)
    first = (await issue(admin, cohort, tid, list(ids.values()))).json()["items"][0]
    r = await admin.post(f"{REG}/{first['id']}/reissue", json={})
    assert r.status_code == 422  # a comment is required
    r = await admin.post(f"{REG}/{first['id']}/reissue", json={"comment": "опечатка в имени"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["number"] == first["number"] and new["verify_code"] != first["verify_code"]
    assert new["id"] != first["id"]
    old = (await admin.get(f"{REG}/{first['id']}")).json()
    assert old["status"] == "replaced" and old["replaced_by_id"] == new["id"]
    got = (await admin.get(f"{REG}/{new['id']}")).json()
    assert got["status"] == "valid" and got["replaces"] == [first["id"]]
    assert got["comment"] == "опечатка в имени"
    # only a valid certificate can be reissued or revoked
    assert (
        await admin.post(f"{REG}/{first['id']}/reissue", json={"comment": "x"})
    ).status_code == 409
    assert (
        await admin.post(f"{REG}/{first['id']}/revoke", json={"reason": "x"})
    ).status_code == 409
    log = (await admin.get("/api/v1/audit", params={"action": "certificate.reissue"})).json()
    assert log["total"] == 1 and "перевыпущен сертификат" in log["items"][0]["text"]


async def test_revoke_needs_a_reason_and_the_right(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 1)
    cert = (await issue(admin, cohort, tid, list(ids.values()))).json()["items"][0]
    viewer = await login_as("viewer", await make_role("Просмотр", {"certificates": "view"}))
    r = await viewer.post(f"{REG}/{cert['id']}/revoke", json={"reason": "ошибка"})
    assert r.status_code == 403
    assert (
        await viewer.post(f"{REG}/{cert['id']}/reissue", json={"comment": "x"})
    ).status_code == 403
    assert (await viewer.get(f"{REG}/{cert['id']}")).status_code == 200
    assert (await admin.post(f"{REG}/{cert['id']}/revoke", json={})).status_code == 422
    assert (await admin.post(f"{REG}/{cert['id']}/revoke", json={"reason": " "})).status_code == 422
    r = await admin.post(f"{REG}/{cert['id']}/revoke", json={"reason": "выдан по ошибке"})
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    got = (await admin.get(f"{REG}/{cert['id']}")).json()
    assert got["revoke_reason"] == "выдан по ошибке" and got["revoked_at"] and got["revoked_by"]
    log = (await admin.get("/api/v1/audit", params={"action": "certificate.revoke"})).json()
    assert "выдан по ошибке" in log["items"][0]["text"]
    # the cohort can issue again after a revoke, with the same number
    again = await issue(admin, cohort, tid, list(ids.values()))
    assert again.status_code == 201 and again.json()["items"][0]["number"] == cert["number"]


# ---- registry --------------------------------------------------------------------------------


async def test_registry_filters_search_and_xlsx(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    c1, ids1 = await graduates(admin, 3, name="A")
    c2, ids2 = await graduates(admin, 2, name="B", branch="Истаравшан")
    items1 = (await issue(admin, c1, tid, list(ids1.values()))).json()["items"]
    await issue(admin, c2, tid, list(ids2.values()))
    await admin.post(f"{REG}/{items1[0]['id']}/revoke", json={"reason": "тест"})
    r = (await admin.get(REG)).json()
    assert r["total"] == 5 and r["page"] == 1 and len(r["items"]) == 5
    assert (await admin.get(REG, params={"status": "revoked"})).json()["total"] == 1
    assert (await admin.get(REG, params={"status": "valid"})).json()["total"] == 4
    assert (await admin.get(REG, params={"cohort_id": c2["id"]})).json()["total"] == 2
    assert (await admin.get(REG, params={"course_id": c1["course_id"]})).json()["total"] == 3
    assert (await admin.get(REG, params={"template_id": tid})).json()["total"] == 5
    assert (await admin.get(REG, params={"template_id": c1["id"]})).json()["total"] == 0
    assert (await admin.get(REG, params={"date_from": "2999-01-01"})).json()["total"] == 0
    assert (await admin.get(REG, params={"date_to": "2000-01-01"})).json()["total"] == 0
    assert (
        await admin.get(REG, params={"date_from": "2000-01-01", "date_to": "2999-01-01"})
    ).json()["total"] == 5
    number = items1[1]["number"]
    found = (await admin.get(REG, params={"q": number})).json()
    assert found["total"] == 1 and found["items"][0]["number"] == number
    assert (await admin.get(REG, params={"q": "студент01"})).json()["total"] == 2
    page = (await admin.get(REG, params={"page_size": 2, "page": 3})).json()
    assert page["total"] == 5 and len(page["items"]) == 1
    branch = (await admin.get(REG, params={"branch_id": c2["branch_id"]})).json()
    assert branch["total"] == 2
    x = await admin.get(REG, params={"format": "xlsx", "status": "valid"})
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    rows = list(load_workbook(io.BytesIO(x.content)).active.iter_rows(values_only=True))  # type: ignore[union-attr]
    assert rows[0][0] == "Номер" and len(rows) == 5
    assert {r[7] for r in rows[1:]} == {"Действует"}


async def test_registry_is_branch_scoped_and_needs_the_right(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    tid = await make_template()
    c1, ids1 = await graduates(admin, 1, name="A")
    c2, ids2 = await graduates(admin, 1, name="B", branch="Истаравшан")
    mine = (await issue(admin, c1, tid, list(ids1.values()))).json()["items"][0]
    foreign = (await issue(admin, c2, tid, list(ids2.values()))).json()["items"][0]
    role = await make_role("Выдача", {"certificates": "change"})
    dsh = await login_as("dsh", role, branch="Душанбе")
    assert (await dsh.get(REG)).json()["total"] == 1
    assert (await dsh.get(f"{REG}/{mine['id']}")).status_code == 200
    for tail in ("", "/pdf"):
        assert (await dsh.get(f"{REG}/{foreign['id']}{tail}")).status_code == 404
    assert (
        await dsh.post(f"{REG}/{foreign['id']}/revoke", json={"reason": "x"})
    ).status_code == 404
    assert (
        await dsh.post(f"{REG}/{foreign['id']}/reissue", json={"comment": "x"})
    ).status_code == 404
    assert (await dsh.get(url(c2, "check"))).status_code == 404
    assert (await issue(dsh, c2, tid, list(ids2.values()))).status_code == 404
    assert (await dsh.get(REG, params={"branch_id": c2["branch_id"]})).status_code == 404
    eid = next(iter(ids2.values()))
    assert (await dsh.post(f"/api/v1/enrollments/{eid}/certificate", json={})).status_code == 404
    none = await login_as("none", await make_role("Без", {"graduates": "change"}))
    assert (await none.get(REG)).status_code == 403
    assert (await none.get(url(c1, "check"))).status_code == 403
    assert (await none.post(f"/api/v1/enrollments/{eid}/certificate", json={})).status_code == 403
    view = await login_as("view", await make_role("Вид", {"certificates": "view"}))
    assert (await view.get(REG)).status_code == 200
    assert (await view.get(url(c1, "check"))).status_code == 403
    assert (await issue(view, c1, tid, list(ids1.values()))).status_code == 403


# ---- the PDF from the snapshot ---------------------------------------------------------------


async def test_pdf_is_rendered_from_the_snapshot_after_later_edits(
    admin: httpx.AsyncClient,
) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 1)
    cert = (await issue(admin, cohort, tid, list(ids.values()))).json()["items"][0]
    first = await admin.get(f"{REG}/{cert['id']}/pdf")
    assert first.status_code == 200 and first.headers["content-type"] == "application/pdf"
    assert "Студент00 Имя" in pdf_text(first.content)
    assert cert["number"] in first.headers["content-disposition"]
    # the student is renamed, the template gets a new version, the director changes
    await sql("UPDATE student SET full_name = 'Другой Человек'")
    await sql(
        "INSERT INTO cert_template_version (template_id, version_no, layout) "
        "SELECT template_id, 2, jsonb_set(layout, '{layers,0,content}', '[{\"text\": \"NEW\"}]') "
        "FROM cert_template_version WHERE version_no = 1"
    )
    await sql("UPDATE cert_settings SET director_name = 'Новый Директор'")
    second = await admin.get(f"{REG}/{cert['id']}/pdf")
    assert pdf_text(second.content) == pdf_text(first.content)
    assert "NEW" not in pdf_text(second.content) and "Другой" not in pdf_text(second.content)
    listed = (await admin.get(REG)).json()["items"][0]
    assert listed["student_name"] == "Студент00 Имя"
    log = (await admin.get("/api/v1/audit", params={"action": "certificate.pdf"})).json()
    assert log["total"] == 2 and "скачан сертификат" in log["items"][0]["text"]
    # a reissue picks the new data up
    new = (await admin.post(f"{REG}/{cert['id']}/reissue", json={"comment": "обновление"})).json()
    fresh = pdf_text((await admin.get(f"{REG}/{new['id']}/pdf")).content)
    assert "NEW" in fresh


async def test_qr_encodes_the_code_with_a_verify_address_and_the_number_without(
    admin: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.certificates import render

    seen: list[str] = []
    original = render._qr_svg

    def spy(address: str, color: str) -> bytes:
        seen.append(address)
        return original(address, color)

    monkeypatch.setattr(render, "_qr_svg", spy)
    tid = await make_template()
    cohort, ids = await graduates(admin, 2)
    a, b = list(ids.values())
    first = (await issue(admin, cohort, tid, [a])).json()["items"][0]
    seen.clear()
    await admin.get(f"{REG}/{first['id']}/pdf")
    assert seen == [f"http://localhost:3200/v/{first['number']}"]
    r = await set_settings(admin, verify_base_url="https://check.example.tj/")
    assert r.status_code == 200 and r.json()["verify_base_url"] == "https://check.example.tj"
    second = (await issue(admin, cohort, tid, [b])).json()["items"][0]
    seen.clear()
    await admin.get(f"{REG}/{second['id']}/pdf")
    assert seen == [f"https://check.example.tj/v/{second['verify_code']}"]
    # an earlier certificate still renders as issued, whatever the setting is now
    await set_settings(admin, verify_base_url=None)
    seen.clear()
    await admin.get(f"{REG}/{second['id']}/pdf")
    assert seen == [f"https://check.example.tj/v/{second['verify_code']}"]
    await admin.get(f"{REG}/{first['id']}/pdf")
    assert seen[-1] == f"http://localhost:3200/v/{first['number']}"


# ---- settings --------------------------------------------------------------------------------


async def test_new_settings_are_superadmin_only_and_validated(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    got = (await admin.get(SETTINGS)).json()
    assert got["verify_base_url"] is None and got["allow_non_graduate"] is False
    editor = await login_as("ed", await make_role("Шаблоны", {"cert_templates": "change"}))
    for body in ({"verify_base_url": "https://a.tj"}, {"allow_non_graduate": True}):
        assert (await set_settings(editor, **body)).status_code == 403
    assert (await set_settings(editor, director_name="Иванов Иван")).status_code == 200
    for bad in (
        "http://a.tj", "https://a.tj/path", "https://a.tj/?q=1", "https://a.tj#x",
        "ftp://a.tj", "https://user@a.tj", "a.tj", "https://",
    ):  # fmt: skip
        r = await set_settings(admin, verify_base_url=bad)
        assert r.status_code == 422, bad
    r = await set_settings(
        admin, verify_base_url="https://verify.ilmhona.tj", allow_non_graduate=True
    )
    assert r.status_code == 200
    assert (r.json()["verify_base_url"], r.json()["allow_non_graduate"]) == (
        "https://verify.ilmhona.tj",
        True,
    )
    assert (await set_settings(admin, verify_base_url="https://v.tj:8443/")).json()[
        "verify_base_url"
    ] == "https://v.tj:8443"
    assert (await set_settings(admin, verify_base_url="")).json()["verify_base_url"] is None
    assert (await set_settings(admin, verify_base_url="https://v.tj")).status_code == 200
    assert (await set_settings(admin, verify_base_url=None)).json()["verify_base_url"] is None
    assert (await set_settings(admin, allow_non_graduate=False)).json()[
        "allow_non_graduate"
    ] is False
    log = (await admin.get("/api/v1/audit", params={"action": "cert_settings.update"})).json()
    assert any("адрес проверки" in i["text"] for i in log["items"])
    assert any("выдача не выпускникам" in i["text"] for i in log["items"])


async def test_a_director_name_that_does_not_fit_is_422_with_template_names(
    admin: httpx.AsyncClient,
) -> None:
    director = {"field": "company.director_name"}
    await make_template(
        "narrow",
        with_layers(
            {**text_layer("d", director, size_pt=20, min_size_pt=12), "w_mm": 40, "h_mm": 8}
        ),
    )
    await make_template("wide", with_layers(text_layer("d", director, size_pt=20)))
    r = await set_settings(admin, director_name="Абдурахмонзода Мухаммадджон")
    assert (r.status_code, r.json()["code"]) == (422, "cert_director_overflow")
    assert r.json()["params"]["templates"] == ["Template narrow"]
    assert (await admin.get(SETTINGS)).json()["director_name"] == "Озодамо Фаромуз"
    assert (await set_settings(admin, director_name="Иванов Иван")).status_code == 200


# ---- migration -------------------------------------------------------------------------------


async def test_migration_0025_up_and_down() -> None:
    name = f"{TEST_DB}_mig_cert"
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

    try:
        await asyncio.to_thread(command.upgrade, cfg, "0024")
        assert await one("SELECT to_regclass('certificate')") is None
        await asyncio.to_thread(command.upgrade, cfg, "0025")
        assert await one("SELECT to_regclass('certificate')") == "certificate"
        assert (
            await one(
                "SELECT count(*) FROM pg_indexes WHERE indexname = 'certificate_one_valid_key'"
            )
            == 1
        )
        assert await one("SELECT allow_non_graduate FROM cert_settings") is False
        await asyncio.to_thread(command.downgrade, cfg, "0024")
        assert await one("SELECT to_regclass('certificate')") is None
        assert (
            await one(
                "SELECT count(*) FROM information_schema.columns WHERE table_name = 'cert_settings' "
                "AND column_name IN ('verify_base_url', 'allow_non_graduate')"
            )
            == 0
        )
        await asyncio.to_thread(command.upgrade, cfg, "head")
        assert await one("SELECT to_regclass('certificate')") == "certificate"
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()
