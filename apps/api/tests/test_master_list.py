"""Stage 4: the master list per cohort."""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta

import httpx

from tests.conftest import sql
from tests.edu import make_course
from tests.reports import ML, employ, student_of, world
from tests.sales import make_lead


async def lead_at(c: httpx.AsyncClient, name: str, course: str, day: date, at: time, status: str,
                  branch: str = "Душанбе") -> None:  # fmt: skip
    lead = await make_lead(c, name, branch=branch, course_id=course)
    await sql(
        "UPDATE lead SET created_at = timezone('Asia/Dushanbe', CAST(:t AS timestamp)), "
        "status = :s WHERE id = :i",
        t=datetime.combine(day, at), s=status, i=lead["id"],
    )  # fmt: skip


async def test_master_list_row_numbers(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    w = await world(admin, browser)
    live = w["live"]
    start = date.fromisoformat(live["start_date"])
    course = live["course_id"]
    # the lead window: 45 days before the start through the start day, same course and branch
    await lead_at(admin, "В окне 1", course, start - timedelta(days=45), time(0, 30), "новый")
    await lead_at(admin, "В окне 2", course, start - timedelta(days=5), time(12), "нулевой урок")
    await lead_at(admin, "В окне 3", course, start, time(23, 30), "записан")
    await lead_at(admin, "Мимо 1", course, start - timedelta(days=46), time(23, 30), "новый")
    await lead_at(admin, "Мимо 2", course, start + timedelta(days=1), time(0, 30), "новый")
    await lead_at(admin, "Мимо 3", course, start, time(12), "новый", branch="Истаравшан")
    await lead_at(admin, "Мимо 4", str(await make_course("Другой")), start, time(12), "новый")
    await lead_at(admin, "Мимо 5", course, start - timedelta(days=3), time(12), "отказ")
    rows = (await admin.get(ML)).json()
    by_code = {r["code"]: r for r in rows["items"]}
    assert rows["total"] == 4
    r = by_code[live["code"]]
    assert (r["leads"], r["zero_lesson"]) == (4, 2)  # the refusal is in the window, not «later»
    assert (r["enrolled"], r["paid_1"], r["paid_2"], r["paid_3"]) == (2, 1, 1, 0)
    assert (r["income"], r["ltv"], r["graduates"], r["employed"]) == ("1000.00", "500.00", 0, 0)
    assert (r["format"], r["price_month"], r["status"]) == ("offline", "500.00", "активный")
    done = by_code[w["done"]["code"]]
    assert (done["enrolled"], done["graduates"], done["income"], done["ltv"]) == (
        2, 1, "300.00", "150.00",
    )  # fmt: skip
    empty = by_code[w["recruiting"]["code"]]
    assert (empty["enrolled"], empty["ltv"], empty["income"]) == (0, None, "0.00")
    await employ(admin, await student_of(w["done_ids"]["Выпускник Один"]))
    rows = (await admin.get(ML)).json()["items"]
    assert next(x for x in rows if x["code"] == w["done"]["code"])["employed"] == 1


async def test_master_list_filters(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    w = await world(admin, browser)

    async def codes(**params: str) -> set[str]:
        items = (await admin.get(ML, params=params)).json()["items"]
        return {r["code"] for r in items}

    assert len(await codes()) == 4
    assert await codes(status="активный") == {w["live"]["code"], w["other"]["code"]}
    assert await codes(status="набор") == {w["recruiting"]["code"]}
    assert await codes(
        branch_id=str((await sql("SELECT id FROM branch WHERE name = 'Истаравшан'"))[0][0])
    ) == {w["other"]["code"]}
    soon = w["recruiting"]["start_date"]
    assert await codes(date_from=soon) == {w["recruiting"]["code"]}
    assert await codes(date_to=w["done"]["start_date"]) <= {
        w["live"]["code"],
        w["done"]["code"],
        w["other"]["code"],
    }
    page = (await admin.get(ML, params={"page_size": 2, "page": 2})).json()
    assert (len(page["items"]), page["total"]) == (2, 4)
