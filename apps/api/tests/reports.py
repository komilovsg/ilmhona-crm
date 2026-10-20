"""Fixtures for the report tests: finished cohorts with graduates, employment, one big world."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx

from app.cli import daily
from app.cohorts.status import today
from tests.conftest import make_user, sign_in, sql
from tests.edu import C, make_cohort, make_course, make_room
from tests.money import enroll, make_payout, pay, running_cohort
from tests.sales import CA, L, make_campaign, make_lead

E = "/api/v1/enrollments"
G = "/api/v1/graduates"
EM = "/api/v1/employment"
D = "/api/v1/dashboard"
ML = "/api/v1/master-list"


async def grade(c: httpx.AsyncClient, enrollment: str, homework: int, final: int) -> None:
    r = await c.patch(f"{E}/{enrollment}/grade", json={"homework": homework, "final": final})
    assert r.status_code == 200, r.text


async def finish(cohort: dict[str, Any]) -> None:
    """The cohort ended yesterday: the daily job closes it and its enrollments."""
    await sql(
        "UPDATE cohort SET end_date = :e WHERE id = :i",
        e=today() - timedelta(days=1),
        i=cohort["id"],
    )
    await daily()


async def finished_cohort(
    admin: httpx.AsyncClient,
    students: dict[str, tuple[int, int]],
    *,
    name: str = "F",
    branch: str = "Душанбе",
    **extra: Any,
) -> tuple[dict[str, Any], dict[str, str]]:
    """A cohort with `students` {name: (homework, final)} that ended yesterday. Attendance is not
    marked, so the total is homework + final. Returns the cohort and {name: enrollment id}."""
    cohort = await make_cohort(
        admin,
        await make_course(f"Курс {name}"),
        await make_room(branch, f"R-{name}"),
        branch=branch,
        start=today() - timedelta(days=20),
        weeks=8,
        **extra,
    )
    ids = {}
    for student, (homework, final) in students.items():
        ids[student] = await enroll(admin, cohort, student, branch=branch)
        await grade(admin, ids[student], homework, final)
    await finish(cohort)
    return cohort, ids


async def employ(
    c: httpx.AsyncClient, student_id: str, organization: str = "ООО Рога", **kw: Any
) -> httpx.Response:
    return await c.post(
        EM,
        json={
            "student_id": student_id,
            "organization": organization,
            "employed_at": today().isoformat(),
            **kw,
        },
    )


async def student_of(enrollment: str) -> str:
    return str((await sql("SELECT student_id FROM enrollment WHERE id = :i", i=enrollment))[0][0])


async def instructor_client(
    browser: Callable[[], httpx.AsyncClient], login: str, branch: str = "Душанбе"
) -> tuple[Any, httpx.AsyncClient]:
    uid = await make_user(login, "instructor", branch=branch)
    c = browser()
    await sign_in(c, login)
    return uid, c


async def world(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> dict[str, Any]:
    """Two branches, five cohorts of every state, money, leads, campaigns, one instructor."""
    ins, ins_client = await instructor_client(browser, "ins1")
    live = await running_cohort(admin, name="Live", instructor_id=str(ins))
    e1 = await enroll(admin, live, "Живой Один")
    e2 = await enroll(admin, live, "Живой Два")
    gone = await enroll(admin, live, "Отчисленный")
    await admin.patch(f"{E}/{gone}", json={"status": "отчислен"})
    await pay(admin, e1, month=1, confirm=True)
    await pay(admin, e1, month=2, confirm=True)
    await pay(admin, e2, month=1)  # pending: not income
    await make_payout(admin, live, amount="400")
    done, done_ids = await finished_cohort(
        admin, {"Выпускник Один": (40, 35), "Выпускник Два": (30, 30)}, instructor_id=str(ins)
    )
    await pay(admin, done_ids["Выпускник Один"], month=1, amount=300, confirm=True)
    recruiting = await make_cohort(
        admin,
        await make_course("Курс Набор"),
        await make_room("Душанбе", "R-Набор"),
        start=today() + timedelta(days=30),
        weeks=8,
    )
    other = await running_cohort(admin, name="Ist", branch="Истаравшан", price=300)
    e3 = await enroll(admin, other, "Истаравшанец", branch="Истаравшан")
    await pay(admin, e3, month=1, amount=300, confirm=True)
    await make_campaign(admin, "Душанбе-кампания", budget=1000, start_date=today().isoformat())
    await make_campaign(
        admin, "Истараравшан-кампания", branch="Истаравшан", budget=200,
        start_date=today().isoformat(),
    )  # fmt: skip
    for i in range(4):
        await make_lead(admin, f"Лид {i}", phone=f"90000000{i}")
    await make_lead(admin, "Лид И", phone="905000000", branch="Истаравшан")
    await sql("UPDATE lead SET status = 'записан' WHERE full_name IN ('Лид 0', 'Лид И')")
    return {
        "instructor": ins,
        "instructor_client": ins_client,
        "live": live,
        "done": done,
        "done_ids": done_ids,
        "recruiting": recruiting,
        "other": other,
    }


_ = (C, CA, L)
