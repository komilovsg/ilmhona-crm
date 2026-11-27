"""Cohort codes are 'G-' + at least 3 digits and keep growing past 999 (no truncation)."""

import httpx

from tests.conftest import sql
from tests.edu import make_cohort, make_course, make_room


async def test_cohort_code_grows_past_999(admin: httpx.AsyncClient) -> None:
    await sql("SELECT setval('cohort_code_seq', 998)")
    course = await make_course("Курс кода")
    a = await make_cohort(admin, course, await make_room(name="R-code-1"))
    b = await make_cohort(admin, course, await make_room(name="R-code-2"))
    assert (a["code"], b["code"]) == ("G-999", "G-1000")
