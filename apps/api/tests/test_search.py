"""One search for every list: phone in any form (≥ 3 digits), ё = е, any case, wildcards literal."""

import httpx

from tests.conftest import make_user, sql
from tests.edu import C, make_student
from tests.money import I, P, enroll, pay, running_cohort

S = "/api/v1/students"
U = "/api/v1/users"
PHONE = "+992 90 123 45 06"
TERMS = ["+992 90 123 45 06", "90 123", "(90) 123-45", "елкин", "ЁЛКИН", "Ёлк"]
SAFE = ["%", "_", "'", "' OR 1=1 --", "\\", "%%", "а_б"]


async def found(c: httpx.AsyncClient, url: str, q: str) -> int:
    r = await c.get(url, params={"q": q, "page_size": 100})
    assert r.status_code == 200, (url, q, r.text)
    return r.json()["total"]  # type: ignore[no-any-return]


async def check(c: httpx.AsyncClient, url: str) -> None:
    for q in TERMS:
        assert await found(c, url, q) == 1, (url, q)
    assert await found(c, url, "zzz") == 0
    for q in SAFE:  # wildcards are literal, nothing matches, nothing breaks
        assert await found(c, url, q) == 0, (url, q)


async def test_students_search(admin: httpx.AsyncClient) -> None:
    await make_student("Ёлкин Иван", phone=PHONE)
    await make_student("Другой", phone="+992 93 000 00 00")
    await check(admin, S)


async def test_payments_and_debtors_search(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, back=1, price=500)
    e = await enroll(admin, cohort, "Ёлкин Иван")
    await sql(
        "UPDATE student SET phone = :p WHERE id = (SELECT student_id FROM enrollment WHERE id = :e)",
        p=PHONE,
        e=e,
    )
    await pay(admin, e, month=1, amount=100, confirm=True)
    await check(admin, P)
    await check(admin, f"{P}/debtors")


async def test_users_and_instructors_search(admin: httpx.AsyncClient) -> None:
    uid = await make_user("elkin", "instructor", phone=PHONE)
    await sql("UPDATE app_user SET full_name = 'Ёлкин Иван' WHERE id = :i", i=uid)
    await make_user("other", "instructor", phone="+992 93 000 00 00")
    for url in (U, I):
        for q in TERMS:
            assert await found(admin, url, q) == 1, (url, q)
        for q in SAFE:
            assert await found(admin, url, q) == 0, (url, q)


async def test_cohort_search_folds_yo_and_case(admin: httpx.AsyncClient) -> None:
    await running_cohort(admin, name="Ёлкин")
    for q in ("елкин", "ЕЛКИН", "ёлкин"):
        assert await found(admin, C, q) == 1, q
    for q in SAFE:
        assert await found(admin, C, q) == 0, q
