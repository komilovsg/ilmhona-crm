"""Certificates C2 security: the instructor scope, a revoked certificate, the verify address, the
Excel export and concurrent issue / reissue / revoke."""

import asyncio
import io
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook

from tests.certs import make_template
from tests.conftest import SignedIn, sql
from tests.edu import instructor_rights
from tests.reports import finished_cohort

REG = "/api/v1/certificates"


@pytest.fixture(autouse=True)
async def fresh_certificate_numbers() -> Any:
    yield
    await sql("ALTER SEQUENCE certificate_no_seq RESTART")


async def graduates(
    admin: httpx.AsyncClient, n: int = 1, **kw: Any
) -> tuple[dict[str, Any], list[str]]:
    cohort, ids = await finished_cohort(
        admin, {f"Студент{i:02d} {kw.get('name', 'F')}": (40, 35) for i in range(n)}, **kw
    )
    await sql("UPDATE student SET gender = 'male'")
    return cohort, list(ids.values())


async def issue(
    c: httpx.AsyncClient, cohort: dict[str, Any], tid: str, ids: list[str]
) -> httpx.Response:
    return await c.post(
        f"/api/v1/cohorts/{cohort['id']}/certificates/issue",
        json={"template_id": tid, "enrollment_ids": ids},
    )


async def test_instructor_sees_only_own_cohort_certificates_and_never_writes(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    tid = await make_template()
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    own, own_ids = await graduates(admin, name="A", instructor_id=me)
    other, other_ids = await graduates(admin, name="B")
    mine = (await issue(admin, own, tid, own_ids)).json()["items"][0]
    foreign = (await issue(admin, other, tid, other_ids)).json()["items"][0]
    async with instructor_rights(certificates="change"):
        listed = (await ins.get(REG)).json()
        assert [i["id"] for i in listed["items"]] == [mine["id"]]
        assert (await ins.get(REG, params={"cohort_id": other["id"]})).json()["total"] == 0
        xlsx = await ins.get(REG, params={"format": "xlsx"})
        assert xlsx.status_code == 200
        assert load_workbook(io.BytesIO(xlsx.content)).active.max_row == 2  # header + own
        assert (await ins.get(f"{REG}/{mine['id']}")).status_code == 200
        for tail in ("", "/pdf"):
            assert (await ins.get(f"{REG}/{foreign['id']}{tail}")).status_code == 404
        # never a write (#24), not even in the own cohort
        for cohort, ids in ((own, own_ids), (other, other_ids)):
            check = await ins.get(f"/api/v1/cohorts/{cohort['id']}/certificates/check")
            assert check.status_code == 403
            assert (await issue(ins, cohort, tid, ids)).status_code == 403
            single = await ins.post(f"/api/v1/enrollments/{ids[0]}/certificate", json={})
            assert single.status_code == 403
        for cert in (mine, foreign):
            r = await ins.post(f"{REG}/{cert['id']}/revoke", json={"reason": "x"})
            assert r.status_code == 403
            r = await ins.post(f"{REG}/{cert['id']}/reissue", json={"comment": "x"})
            assert r.status_code == 403
    assert (await sql("SELECT count(*) FROM certificate WHERE status = 'valid'"))[0][0] == 2


async def test_revoked_certificate_is_not_rendered_by_the_graduates_pdf(
    admin: httpx.AsyncClient,
) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin)
    cert = (await issue(admin, cohort, tid, ids)).json()["items"][0]
    pdf = f"/api/v1/graduates/{ids[0]}/certificate/pdf"
    assert (await admin.get(pdf)).status_code == 200
    r = await admin.post(f"{REG}/{cert['id']}/revoke", json={"reason": "выдан по ошибке"})
    assert r.status_code == 200
    r = await admin.get(pdf)
    assert (r.status_code, r.json()["code"]) == (409, "cert_not_valid")
    # issued again: the PDF is back
    assert (await issue(admin, cohort, tid, ids)).status_code == 201
    assert (await admin.get(pdf)).status_code == 200


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "http://check.example.org",
        "https://check.example.org/v",
        "https://user@check.example.org",
        "https://check.example.org?x=1",
        "https://ex<am>ple.org",
        'https://ex"ample.org',
        "https://a b.org",
        "https://good.org\\.evil.org",
        "https://" + "a" * 250 + ".org",
    ],
)
async def test_verify_base_url_rejects_anything_but_an_https_host(
    admin: httpx.AsyncClient, value: str
) -> None:
    r = await admin.patch("/api/v1/cert-settings", json={"verify_base_url": value})
    assert r.status_code == 422, (value, r.text)


async def test_verify_base_url_keeps_a_plain_host_and_port(admin: httpx.AsyncClient) -> None:
    r = await admin.patch(
        "/api/v1/cert-settings", json={"verify_base_url": " https://Check.Example.org:8443/ "}
    )
    assert r.status_code == 200, r.text
    assert r.json()["verify_base_url"] == "https://check.example.org:8443"
    r = await admin.patch("/api/v1/cert-settings", json={"verify_base_url": ""})
    assert r.status_code == 200 and r.json()["verify_base_url"] is None


async def test_registry_xlsx_neutralises_a_formula_in_the_comment(
    admin: httpx.AsyncClient,
) -> None:
    await make_template()
    _, ids = await graduates(admin)
    evil = '=HYPERLINK("http://x.example","click")'
    r = await admin.post(f"/api/v1/enrollments/{ids[0]}/certificate", json={"comment": evil})
    assert r.status_code == 201, r.text
    cert = r.json()
    r = await admin.post(f"{REG}/{cert['id']}/revoke", json={"reason": "@SUM(1+1)"})
    assert r.status_code == 200
    xlsx = await admin.get(REG, params={"format": "xlsx", "q": "%_\\"})
    assert xlsx.status_code == 200
    xlsx = await admin.get(REG, params={"format": "xlsx"})
    sheet = load_workbook(io.BytesIO(xlsx.content)).active
    cells = [c.value for c in sheet[2]]
    assert "'" + evil in cells and "'@SUM(1+1)" in cells
    assert not any(isinstance(v, str) and v.startswith(("=", "@")) for v in cells)


async def test_parallel_single_issues_reissues_and_revokes_leave_one_valid(
    admin: httpx.AsyncClient,
) -> None:
    await make_template()
    _, ids = await graduates(admin)
    single = f"/api/v1/enrollments/{ids[0]}/certificate"
    a, b = await asyncio.gather(admin.post(single, json={}), admin.post(single, json={}))
    assert sorted((a.status_code, b.status_code)) == [201, 409]
    first = (a if a.status_code == 201 else b).json()
    a, b = await asyncio.gather(
        admin.post(f"{REG}/{first['id']}/reissue", json={"comment": "опечатка"}),
        admin.post(f"{REG}/{first['id']}/reissue", json={"comment": "опечатка"}),
    )
    assert sorted((a.status_code, b.status_code)) == [201, 409]
    second = (a if a.status_code == 201 else b).json()
    assert second["number"] == first["number"]
    a, b = await asyncio.gather(
        admin.post(f"{REG}/{second['id']}/revoke", json={"reason": "ошибка"}),
        admin.post(f"{REG}/{second['id']}/reissue", json={"comment": "ещё раз"}),
    )
    assert sorted((a.status_code, b.status_code)) in ([200, 409], [201, 409])
    rows = await sql("SELECT number, status FROM certificate WHERE enrollment_id = :e", e=ids[0])
    assert len({n for n, _ in rows}) == 1
    assert sum(1 for _, s in rows if s == "valid") <= 1
