"""Certificates C3: the public check page `/v/<code>` (no login), the code under the QR, and the
status rule of a non-graduate who holds a certificate."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.certificates import public
from app.certificates.issuing import CODE_ALPHABET
from app.core.clock import TZ
from tests.certs import layout, make_template, text_layer
from tests.conftest import make_client, sql
from tests.test_certificate_registry import (  # noqa: F401  (autouse: numbers restart)
    REG,
    fresh_certificate_numbers,
    graduates,
    issue,
    mixed,
    set_settings,
)

PUB = "/api/v1/public/certificates"
KEYS = {
    "number", "holder", "course", "cohort_start", "cohort_end", "issued_on", "status",
    "revoked_on", "issuer",
}  # fmt: skip


@pytest.fixture(autouse=True)
def fresh_limits() -> Iterator[None]:
    public.PER_ADDRESS.reset()
    public.EVERYONE.reset()
    yield
    public.PER_ADDRESS.reset()
    public.EVERYONE.reset()


async def one(admin: httpx.AsyncClient, lay: dict[str, Any] | None = None) -> dict[str, Any]:
    tid = await make_template(lay=lay)
    cohort, ids = await graduates(admin, 1)
    r = await issue(admin, cohort, tid, list(ids.values()))
    assert r.status_code == 201, r.text
    return dict(r.json()["items"][0])


async def code_of(cert_id: str) -> str:
    return str((await sql("SELECT public_code FROM certificate WHERE id = :i", i=cert_id))[0][0])


def today() -> str:
    return datetime.now(TZ).date().isoformat()


async def test_a_new_certificate_checks_without_a_login_with_exactly_the_public_fields(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    cert = await one(admin)
    code = await code_of(cert["id"])
    assert code == cert["verify_code"] and len(code) == 12 and set(code) <= set(CODE_ALPHABET)
    r = await client.get(f"{PUB}/{code}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == KEYS
    assert body == {
        "number": cert["number"],
        "holder": "Студент00 Имя",
        "course": body["course"],
        "cohort_start": None,  # the default template shows no cohort dates
        "cohort_end": None,
        "issued_on": today(),
        "status": "valid",
        "revoked_on": None,
        "issuer": "ilmhona",
    }
    assert body["course"]
    assert r.headers["cache-control"] == "no-store"
    # typed by hand from the paper: lower case, dashes, spaces
    typed = f" {code[:4].lower()}-{code[4:8]} {code[8:]} "
    assert (await client.get(f"{PUB}/{typed}")).json() == body


async def test_cohort_dates_show_only_when_the_certificate_prints_them(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    lay = layout()
    lay["layers"].append(
        {
            **text_layer(
                "period", {"field": "cohort.start_date"}, {"text": " — "},
                {"field": "cohort.end_date"}, size_pt=10,
            ),
            "y_mm": 120, "h_mm": 8,
        }
    )  # fmt: skip
    cert = await one(admin, lay)
    body = (await client.get(f"{PUB}/{await code_of(cert['id'])}")).json()
    assert body["cohort_start"] and body["cohort_end"]
    assert body["cohort_start"] <= body["cohort_end"]


async def test_revoked_shows_revoked_with_the_date_and_never_the_reason(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    cert = await one(admin)
    code = await code_of(cert["id"])
    r = await admin.post(f"{REG}/{cert['id']}/revoke", json={"reason": "подделка печати XYZ"})
    assert r.status_code == 200, r.text
    r = await client.get(f"{PUB}/{code}")
    body = r.json()
    assert (body["status"], body["revoked_on"]) == ("revoked", today())
    assert "XYZ" not in r.text and "подделка" not in r.text


async def test_reissue_rotates_the_code_and_the_old_one_says_replaced_only(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    cert = await one(admin)
    old = await code_of(cert["id"])
    new = (await admin.post(f"{REG}/{cert['id']}/reissue", json={"comment": "опечатка"})).json()
    fresh = await code_of(new["id"])
    assert fresh != old
    was = (await client.get(f"{PUB}/{old}")).json()
    assert set(was) == KEYS and was["status"] == "replaced" and was["revoked_on"] is None
    assert fresh not in str(was) and new["id"] not in str(was)
    assert (await client.get(f"{PUB}/{fresh}")).json()["status"] == "valid"


async def test_unknown_malformed_numbers_and_old_certificates_get_the_same_not_found(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    cert = await one(admin)
    # a certificate issued before the check page: no public code, not checkable by its old code
    await sql("UPDATE certificate SET public_code = NULL WHERE id = :i", i=cert["id"])
    bodies = []
    for probe in (
        cert["verify_code"],
        cert["number"],
        "ZZZZZZZZZZZZ",
        "abc",
        "%27%20OR%201=1--",
        "A" * 300,
        "..%2F..%2Fapi%2Fv1%2Fme",
    ):
        r = await client.get(f"{PUB}/{probe}")
        assert r.status_code == 404, (probe, r.text)
        bodies.append({k: v for k, v in r.json().items() if k != "instance"})
    assert all(b == bodies[0] for b in bodies)
    assert bodies[0]["code"] == "not_found"


async def test_the_code_is_random_not_derived_from_the_number(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 12)
    items = (await issue(admin, cohort, tid, list(ids.values()))).json()["items"]
    codes = [await code_of(i["id"]) for i in items]
    assert len(set(codes)) == 12
    for item, code in zip(items, codes, strict=True):
        digits = item["number"].split("-")[-1]
        assert digits not in code and item["number"] not in code
    # consecutive numbers share no common prefix structure that would let one code predict another
    assert len({c[:4] for c in codes}) > 6


async def test_public_route_opens_nothing_else_and_views_are_not_audited(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    cert = await one(admin)
    code = await code_of(cert["id"])
    for path in (
        REG,
        f"{REG}/{cert['id']}",
        f"{REG}/{cert['id']}/pdf",
        "/api/v1/cert-settings",
        "/api/v1/auth/me",
    ):
        assert (await client.get(path)).status_code == 401, path
    assert (await client.get(PUB)).status_code in (404, 405)
    assert (await client.post(f"{PUB}/{code}")).status_code in (403, 405)
    before = (await sql("SELECT count(*) FROM audit_log"))[0][0]
    for _ in range(3):
        assert (await client.get(f"{PUB}/{code}")).status_code == 200
    assert (await sql("SELECT count(*) FROM audit_log"))[0][0] == before


async def test_checks_are_rate_limited_per_address(admin: httpx.AsyncClient) -> None:
    cert = await one(admin)
    code = await code_of(cert["id"])
    async with make_client("10.0.0.7") as a, make_client("10.0.0.8") as b:
        got = [(await a.get(f"{PUB}/ZZZZZZZZZZZZ")).status_code for _ in range(20)]
        assert got == [404] * 20
        r = await a.get(f"{PUB}/{code}")
        assert (r.status_code, r.json()["code"]) == (429, "cert_check_limit")
        assert (await b.get(f"{PUB}/{code}")).status_code == 200


async def test_the_pdf_prints_the_code_under_the_qr(admin: httpx.AsyncClient) -> None:
    from tests.test_certificate_registry import pdf_text

    cert = await one(admin)
    code = await code_of(cert["id"])
    text = pdf_text((await admin.get(f"{REG}/{cert['id']}/pdf")).content)
    assert f"{code[:4]}-{code[4:8]}-{code[8:]}" in text


async def test_a_non_graduate_holder_keeps_an_editable_status_a_graduate_does_not(
    admin: httpx.AsyncClient,
) -> None:
    await make_template()
    _, ids = await mixed(admin)
    await set_settings(admin, allow_non_graduate=True)
    weak = ids["Слабый Иван"]
    r = await admin.post(f"/api/v1/enrollments/{weak}/certificate", json={"comment": "решение"})
    assert r.status_code == 201, r.text
    r = await admin.patch(f"/api/v1/enrollments/{weak}", json={"status": "отчислен"})
    assert r.status_code == 200, r.text
    r = await admin.patch(f"/api/v1/enrollments/{weak}", json={"status": "завершил"})
    assert r.status_code == 200, r.text
    strong = ids["Студент00 Имя"]
    r = await admin.post(f"/api/v1/enrollments/{strong}/certificate", json={})
    assert r.status_code == 201, r.text
    r = await admin.patch(f"/api/v1/enrollments/{strong}", json={"status": "завершил"})
    assert (r.status_code, r.json()["code"]) == (409, "certificate_issued")
