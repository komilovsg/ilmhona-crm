"""Academy goal text, goals with automatic progress, private notes."""

import uuid
from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from app.metrics.goals import pace
from app.metrics.money import today
from tests.conftest import SignedIn, branch_id, make_role, sql
from tests.edu import make_cohort, make_course, make_room
from tests.money import add_months, enroll, pay, running_cohort

AG = "/api/v1/academy/goal"
G = "/api/v1/goals"
N = "/api/v1/notes"
A = "/api/v1/audit"


def v(version: int) -> dict[str, str]:
    return {"X-Record-Version": str(version)}


async def mk_goal(c: httpx.AsyncClient, **kw: Any) -> dict[str, Any]:
    body = {
        "title": "Цель",
        "metric": "new_enrollments",
        "target": 10,
        "start_date": (today() - timedelta(days=30)).isoformat(),
        "deadline": (today() + timedelta(days=30)).isoformat(),
        **kw,
    }
    r = await c.post(G, json=body)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def mk_note(c: httpx.AsyncClient, text: str = "Заметка", **kw: Any) -> dict[str, Any]:
    r = await c.post(N, json={"text": text, **kw})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def clients(login_as: SignedIn) -> dict[str, httpx.AsyncClient]:
    manager = await make_role("Менеджер (тест)", {"dashboard": "view", "cohorts": "change"})
    everything = await make_role(
        "Все права кроме филиала",
        {s: "change" for s in ("dashboard", "leads", "students", "cohorts", "users", "audit")},
    )
    return {
        "super": await login_as("root", "superadmin"),
        "admin": await login_as("adm", everything),
        "branch_manager": await login_as("mgr", manager, branch="Душанбе"),
        "instructor": await login_as("ins", "instructor", branch="Душанбе"),
    }


# ---- permissions matrix --------------------------------------------------------------------


async def test_unauthenticated_gets_401_everywhere(client: httpx.AsyncClient) -> None:
    h = {"X-Requested-With": "ilm", **v(1)}
    for method, url in (
        ("GET", AG),
        ("PATCH", AG),
        ("GET", G),
        ("POST", G),
        ("PATCH", f"{G}/{uuid.uuid4()}"),
        ("POST", f"{G}/{uuid.uuid4()}/archive"),
        ("GET", N),
        ("POST", N),
        ("PATCH", f"{N}/{uuid.uuid4()}"),
        ("DELETE", f"{N}/{uuid.uuid4()}"),
    ):
        r = await client.request(method, url, headers=h, json={})
        assert r.status_code == 401, (method, url, r.status_code)


async def test_everyone_signed_in_reads_the_academy_goal_only_superadmin_sets_it(
    login_as: SignedIn,
) -> None:
    c = await clients(login_as)
    for name, who in c.items():
        r = await who.get(AG)
        assert r.status_code == 200, name
        assert r.json()["text"] == ""
    version = (await c["super"].get(AG)).json()["version"]
    for name in ("admin", "branch_manager", "instructor"):
        r = await c[name].patch(AG, json={"text": "Чужая"}, headers=v(version))
        assert r.status_code == 403, name
    r = await c["super"].patch(
        AG, json={"text": "К лету 2027 — 1 000 выпускников"}, headers=v(version)
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "К лету 2027 — 1 000 выпускников"
    assert r.json()["version"] == version + 1
    for who in c.values():
        assert (await who.get(AG)).json()["text"] == "К лету 2027 — 1 000 выпускников"


async def test_goals_and_notes_are_closed_to_everyone_but_the_superadmin(
    login_as: SignedIn,
) -> None:
    c = await clients(login_as)
    goal = await mk_goal(c["super"])
    note = await mk_note(c["super"])
    for name in ("admin", "branch_manager", "instructor"):
        who = c[name]
        assert (await who.get(G)).status_code == 403, name
        assert (await who.post(G, json={"title": "x"})).status_code == 403, name
        r = await who.patch(f"{G}/{goal['id']}", json={"title": "x"}, headers=v(1))
        assert r.status_code == 403, name
        assert (await who.post(f"{G}/{goal['id']}/archive", headers=v(1))).status_code == 403
        assert (await who.get(N)).status_code == 403, name
        assert (await who.post(N, json={"text": "x"})).status_code == 403, name
        assert (await who.delete(f"{N}/{note['id']}")).status_code == 403, name
        r = await who.patch(f"{N}/{note['id']}", json={"text": "x"}, headers=v(1))
        assert r.status_code == 403, name


# ---- academy goal --------------------------------------------------------------------------


async def test_academy_goal_limits_conflict_and_audit(admin: httpx.AsyncClient) -> None:
    start = (await admin.get(AG)).json()["version"]
    r = await admin.patch(AG, json={"text": "я" * 281}, headers=v(start))
    assert r.status_code == 422
    r = await admin.patch(AG, json={"text": "я" * 280}, headers=v(start))
    assert r.status_code == 200
    version = r.json()["version"]
    r = await admin.patch(AG, json={"text": "Новая"}, headers=v(version - 1))
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    assert r.json()["params"]["current"]["text"] == "я" * 280
    assert (await admin.patch(AG, json={"text": "Новая"}, no_version=True)).status_code == 428
    assert (await admin.patch(AG, json={"text": "Новая"}, headers=v(version))).status_code == 200
    items = (await admin.get(A, params={"action": "academy_goal.update"})).json()["items"]
    assert items[0]["text"].endswith("Цель академии изменена: «Новая»")


# ---- goals CRUD ----------------------------------------------------------------------------


async def test_goal_crud_archive_audit_and_validation(admin: httpx.AsyncClient) -> None:
    goal = await mk_goal(admin, title="  Набор  ", target="25")
    assert goal["title"] == "Набор" and goal["target"] == 25 and goal["branch_id"] is None
    assert goal["current"] == 0 and goal["notes_count"] == 0
    bad = {
        "title": "",
        "metric": "nope",
        "target": 0,
        "start_date": "2026-01-01",
        "deadline": "2026-02-01",
    }
    assert (await admin.post(G, json=bad)).status_code == 422
    assert (
        await admin.post(G, json={**bad, "title": "x" * 121, "metric": "income", "target": 1})
    ).status_code == 422
    r = await admin.post(
        G,
        json={**bad, "title": "t", "metric": "income", "target": 1, "deadline": "2026-01-01"},
    )
    assert (r.status_code, r.json()["code"]) == (422, "goal_dates_invalid")
    r = await admin.post(
        G, json={**bad, "title": "t", "metric": "collection_rate_month", "target": 101}
    )
    assert r.status_code == 422
    r = await admin.patch(f"{G}/{goal['id']}", json={"target": "30"}, headers=v(goal["version"]))
    assert r.status_code == 200 and r.json()["target"] == 30
    r = await admin.patch(f"{G}/{goal['id']}", json={"target": "40"}, headers=v(goal["version"]))
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    r = await admin.patch(
        f"{G}/{goal['id']}",
        json={"deadline": "2000-01-01"},
        headers=v(r.json()["params"]["version"]),
    )
    assert r.json()["code"] == "goal_dates_invalid"
    r = await admin.patch(f"{G}/{goal['id']}", json={"branch_id": str(uuid.uuid4())}, headers=v(2))
    assert r.status_code == 404
    r = await admin.post(f"{G}/{goal['id']}/archive", headers=v(2))
    assert r.status_code == 200 and r.json()["archived"] is True
    assert (await admin.get(G)).json()["items"] == []
    assert len((await admin.get(G, params={"archived": "true"})).json()["items"]) == 1
    r = await admin.post(f"{G}/{goal['id']}/unarchive", headers=v(3))
    assert r.json()["archived"] is False
    assert (await admin.delete(f"{G}/{goal['id']}")).status_code == 405  # no hard delete
    sentences = [i["text"] for i in (await admin.get(A, params={"entity": "goal"})).json()["items"]]
    assert any("создана цель Набор" in s for s in sentences)
    assert any("изменена цель Набор — план 25 → 30" in s for s in sentences)
    assert any("архивирована цель Набор" in s for s in sentences)
    assert any("возвращена из архива цель Набор" in s for s in sentences)


# ---- pace math -----------------------------------------------------------------------------

START, END = date(2027, 1, 1), date(2027, 1, 11)  # ten days


@pytest.mark.parametrize(
    ("on", "current", "expected", "status"),
    [
        (date(2026, 12, 20), 0, 0.0, "по графику"),  # before the start: expected 0
        (START, 0, 0.0, "по графику"),  # start day: nothing is expected yet
        (date(2027, 1, 6), 4, 50.0, "отстаём"),  # half of the time, 40 % done
        (date(2027, 1, 6), 5, 50.0, "по графику"),  # exactly on the line
        (END, 9, 100.0, "отстаём"),  # the deadline day is still a day to do it
        (END, 10, 100.0, "достигнута"),
        (date(2027, 1, 12), 9, 100.0, "срок прошёл"),
        (date(2027, 1, 12), 12, 100.0, "достигнута"),  # reached late is still reached
    ],
)
def test_pace_cumulative(on: date, current: float, expected: float, status: str) -> None:
    r = pace("income", current, 10, START, END, on)
    assert (r["expected_pct"], r["status"]) == (expected, status)
    assert r["on_pace"] == (r["progress_pct"] >= expected)
    assert r["progress_pct"] <= 100


def test_pace_rate_metric_expects_the_target_all_the_time() -> None:
    mid = date(2027, 1, 6)
    r = pace("collection_rate_month", 80, 90, START, END, mid)
    assert (r["expected_pct"], r["on_pace"], r["status"]) == (100.0, False, "отстаём")
    r = pace("collection_rate_month", 90, 90, START, END, START)
    assert (r["on_pace"], r["status"]) == (True, "достигнута")


async def test_goal_status_uses_the_clock(admin: httpx.AsyncClient) -> None:
    goal = await mk_goal(
        admin,
        target=5,
        start_date=(today() - timedelta(days=10)).isoformat(),
        deadline=(today() - timedelta(days=1)).isoformat(),
    )
    assert goal["status"] == "срок прошёл" and goal["expected_pct"] == 100.0
    goal = await mk_goal(
        admin, start_date=today().isoformat(), deadline=(today() + timedelta(days=9)).isoformat()
    )
    assert (goal["expected_pct"], goal["status"]) == (0.0, "по графику")


# ---- metrics against independent SQL --------------------------------------------------------


async def one(query: str, **params: Any) -> float:
    return float((await sql(query, **params))[0][0])


async def seed(admin: httpx.AsyncClient) -> dict[str, Any]:
    """Two branches: Душанбе has a running cohort (price 500) with 3 students, Истаравшан one with 2."""
    d = await running_cohort(admin, name="D", back=2, price=500)
    i = await running_cohort(admin, name="I", branch="Истаравшан", back=1, price=300)
    d1 = await enroll(admin, d, "Д1")
    d2 = await enroll(admin, d, "Д2")
    await enroll(admin, d, "Д3")
    i1 = await enroll(admin, i, "И1", branch="Истаравшан")
    await enroll(admin, i, "И2", branch="Истаравшан")
    this = today().replace(day=1)
    # Душанбе: 2 confirmed + 1 pending for the current month (month 3), one old month confirmed
    await pay(admin, d1, month=3, amount=500, confirm=True, paid_at=today())
    await pay(admin, d2, month=3, amount=200, confirm=True, paid_at=today())
    await pay(admin, d2, month=2, amount=500, confirm=True, paid_at=add_months(this, -1))
    await pay(admin, d1, month=2, amount=100, paid_at=add_months(this, -1))  # pending: never counts
    await pay(admin, i1, month=2, amount=300, confirm=True, paid_at=today())
    # graduates: Душанбе d1 (their cohort ended today), Истаравшан i1 (their cohort ends later)
    await sql("UPDATE enrollment SET status = 'выпускник' WHERE id IN (:a, :b)", a=d1, b=i1)
    await sql("UPDATE cohort SET end_date = :e WHERE id = :i", e=today(), i=d["id"])
    return {"d": d, "i": i}


WINDOW = {
    "start_date": (today() - timedelta(days=100)).isoformat(),
    "deadline": (today() + timedelta(days=100)).isoformat(),
}


async def value(admin: httpx.AsyncClient, metric: str, **kw: Any) -> float:
    goal = await mk_goal(admin, metric=metric, **{"target": 100, **WINDOW, **kw})
    return float(goal["current"])


async def test_metric_graduates_total(admin: httpx.AsyncClient) -> None:
    await seed(admin)
    q = (
        "SELECT count(*) FROM enrollment e JOIN cohort c ON c.id = e.cohort_id "
        "WHERE e.status = 'выпускник' AND c.end_date BETWEEN :a AND :b"
    )
    a, b = date.fromisoformat(WINDOW["start_date"]), date.fromisoformat(WINDOW["deadline"])
    assert await value(admin, "graduates_total") == await one(q, a=a, b=b) == 2
    # the period cuts by the end of the cohort: until today only Душанбе has finished
    until = {"deadline": today().isoformat()}
    assert await value(admin, "graduates_total", **until) == await one(q, a=a, b=today()) == 1
    dushanbe = await branch_id("Душанбе")
    assert await value(admin, "graduates_total", branch_id=str(dushanbe)) == 1
    ist = await branch_id("Истаравшан")
    assert await value(admin, "graduates_total", branch_id=str(ist)) == 1
    assert await value(admin, "graduates_total", branch_id=str(ist), **until) == 0


async def test_metric_active_students(admin: httpx.AsyncClient) -> None:
    await seed(admin)
    q = (
        "SELECT count(*) FROM student s WHERE EXISTS (SELECT 1 FROM enrollment e "
        "WHERE e.student_id = s.id AND e.status = 'активный')"
    )
    assert await value(admin, "active_students") == await one(q) == 3
    ist = await branch_id("Истаравшан")
    assert await value(admin, "active_students", branch_id=str(ist)) == await one(
        q + " AND s.branch_id = :b", b=ist
    )


async def test_metric_income(admin: httpx.AsyncClient) -> None:
    await seed(admin)
    a, b = date.fromisoformat(WINDOW["start_date"]), date.fromisoformat(WINDOW["deadline"])
    q = (
        "SELECT coalesce(sum(p.amount), 0) FROM payment p JOIN enrollment e ON e.id = p.enrollment_id "
        "JOIN cohort c ON c.id = e.cohort_id WHERE p.status = 'подтверждено' "
        "AND p.paid_at BETWEEN :a AND :b"
    )
    assert await value(admin, "income") == await one(q, a=a, b=b) == 1500
    dushanbe = await branch_id("Душанбе")
    assert await value(admin, "income", branch_id=str(dushanbe)) == await one(
        q + " AND c.branch_id = :br", a=a, b=b, br=dushanbe
    )
    # a window that starts tomorrow sees nothing
    assert await value(admin, "income", start_date=(today() + timedelta(days=1)).isoformat()) == 0


async def test_metric_new_enrollments(admin: httpx.AsyncClient) -> None:
    seeded = await seed(admin)
    a, b = date.fromisoformat(WINDOW["start_date"]), date.fromisoformat(WINDOW["deadline"])
    q = (
        "SELECT count(*) FROM enrollment e JOIN cohort c ON c.id = e.cohort_id "
        "WHERE c.status <> 'отменён' "
        "AND (e.enrolled_at AT TIME ZONE 'Asia/Dushanbe')::date BETWEEN :a AND :b"
    )
    assert await value(admin, "new_enrollments") == await one(q, a=a, b=b) == 5
    ist = await branch_id("Истаравшан")
    assert await value(admin, "new_enrollments", branch_id=str(ist)) == 2
    # enrollments are dated by their start day: the second cohort started a month ago
    window = {
        "start_date": (today() - timedelta(days=45)).isoformat(),
        "deadline": (today() + timedelta(days=5)).isoformat(),
    }
    assert await value(admin, "new_enrollments", **window) == await one(
        q, a=date.fromisoformat(window["start_date"]), b=date.fromisoformat(window["deadline"])
    )
    _ = seeded


async def test_metric_courses_launched_uses_the_first_cohort_of_a_course(
    admin: httpx.AsyncClient,
) -> None:
    this = today().replace(day=1)
    python = await make_course("Python", 500)
    design = await make_course("Дизайн", 500)
    room = await make_room("Душанбе", "R1")
    # Python: first cohort 3 months ago, a second one now -> launched 3 months ago, not now
    await make_cohort(admin, python, room, start=add_months(this, -3), weeks=3)
    await make_cohort(admin, python, room, start=this + timedelta(days=1), weeks=3, weekdays=[2])
    # Дизайн: first cohort inside the last 2 months
    await make_cohort(admin, design, room, start=add_months(this, -1), weeks=3, weekdays=[4])
    window = {
        "start_date": add_months(this, -2).isoformat(),
        "deadline": (today() + timedelta(days=60)).isoformat(),
    }
    q = (
        "SELECT count(*) FROM (SELECT course_id, min(start_date) f FROM cohort "
        "WHERE status <> 'отменён' GROUP BY course_id) t WHERE f BETWEEN :a AND :b"
    )
    got = await value(admin, "courses_launched", **window)
    assert got == await one(
        q, a=date.fromisoformat(window["start_date"]), b=date.fromisoformat(window["deadline"])
    )
    assert got == 1
    ist = await branch_id("Истаравшан")
    assert await value(admin, "courses_launched", branch_id=str(ist), **window) == 0


async def test_metric_collection_rate_month_counts_confirmed_of_expected(
    admin: httpx.AsyncClient,
) -> None:
    await seed(admin)
    # this month: Душанбе d1 500/500, d2 200/500, d3 0/500; Истаравшан (started 1 month ago,
    # so this is its month 2) i1 300/300, i2 0/300
    rate = await value(admin, "collection_rate_month", target=90)
    assert rate == round((500 + 200 + 300) * 100 / (1500 + 600), 1)
    dushanbe = await branch_id("Душанбе")
    assert await value(admin, "collection_rate_month", branch_id=str(dushanbe)) == round(
        700 * 100 / 1500, 1
    )


async def test_collection_rate_without_expected_payments_is_zero(admin: httpx.AsyncClient) -> None:
    goal = await mk_goal(admin, metric="collection_rate_month", target=90)
    assert goal["current"] == 0 and goal["status"] == "отстаём"


# ---- notes ---------------------------------------------------------------------------------


async def test_notes_are_private_even_between_two_superadmins(login_as: SignedIn) -> None:
    a = await login_as("a", "superadmin")
    b = await login_as("b", "superadmin")
    note = await mk_note(a, "Секретное мнение про курс")
    assert (await b.get(N)).json()["items"] == []
    assert (await b.get(N, params={"q": "Секретное"})).json()["items"] == []
    r = await b.patch(f"{N}/{note['id']}", json={"text": "взлом"}, headers=v(note["version"]))
    assert r.status_code == 404
    assert (await b.delete(f"{N}/{note['id']}")).status_code == 404
    assert (await sql("SELECT text FROM note"))[0][0] == "Секретное мнение про курс"
    assert len((await a.get(N)).json()["items"]) == 1
    # a goal's note count is the caller's own
    goal = await mk_goal(a)
    await mk_note(a, "к цели", goal_id=goal["id"])
    await mk_note(b, "чужая к цели", goal_id=goal["id"])
    assert (await a.get(G)).json()["items"][0]["notes_count"] == 1
    assert (await b.get(G)).json()["items"][0]["notes_count"] == 1
    assert len((await a.get(N, params={"goal_id": goal["id"]})).json()["items"]) == 1


async def test_notes_crud_filters_search_and_links(admin: httpx.AsyncClient) -> None:
    course = await make_course("Python", 500)
    room = await make_room()
    cohort = await make_cohort(admin, course, room)
    goal = await mk_goal(admin, title="Цель А")
    first = await mk_note(admin, "про 100% и _ знак")
    second = await mk_note(
        admin, "про поток", goal_id=goal["id"], course_id=str(course), cohort_id=cohort["id"]
    )
    assert second["goal_title"] == "Цель А" and second["course_name"] == "Python"
    assert second["cohort_code"] == cohort["code"]
    items = (await admin.get(N)).json()["items"]
    assert [i["id"] for i in items] == [second["id"], first["id"]]  # newest first
    assert len((await admin.get(N, params={"q": "100%"})).json()["items"]) == 1
    assert len((await admin.get(N, params={"q": "%"})).json()["items"]) == 1  # a literal percent
    assert len((await admin.get(N, params={"course_id": str(course)})).json()["items"]) == 1
    assert len((await admin.get(N, params={"cohort_id": cohort["id"]})).json()["items"]) == 1
    r = await admin.patch(
        f"{N}/{second['id']}",
        json={"text": "новый текст", "goal_id": None},
        headers=v(second["version"]),
    )
    assert (
        r.status_code == 200 and r.json()["goal_id"] is None and r.json()["text"] == "новый текст"
    )
    r = await admin.patch(f"{N}/{second['id']}", json={"text": "ещё"}, headers=v(second["version"]))
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    r = await admin.patch(
        f"{N}/{second['id']}",
        json={"goal_id": str(uuid.uuid4())},
        headers=v(r.json()["params"]["version"]),
    )
    assert r.status_code == 404
    assert (await admin.delete(f"{N}/{first['id']}")).status_code == 204
    assert (await admin.delete(f"{N}/{first['id']}")).status_code == 404
    assert len((await admin.get(N)).json()["items"]) == 1


async def test_note_links_set_null_when_the_target_goes(admin: httpx.AsyncClient) -> None:
    goal = await mk_goal(admin)
    note = await mk_note(admin, "x", goal_id=goal["id"])
    await sql("DELETE FROM goal WHERE id = :i", i=goal["id"])
    assert (await admin.get(N)).json()["items"][0]["goal_id"] is None
    _ = note


async def test_note_validation_limits(admin: httpx.AsyncClient) -> None:
    for text in ("", "   ", "я" * 2001):
        assert (await admin.post(N, json={"text": text})).status_code == 422, len(text)
    assert (await admin.post(N, json={"text": "я" * 2000})).status_code == 201
    assert (await admin.post(N, json={"text": "ok", "unknown": 1})).status_code == 422
    assert (
        await admin.post(N, json={"text": "ok", "goal_id": str(uuid.uuid4())})
    ).status_code == 404
    assert (await admin.get(N, params={"limit": 0})).status_code == 422
    assert (await admin.get(N, params={"limit": 201})).status_code == 422


async def test_note_audit_has_no_text(admin: httpx.AsyncClient) -> None:
    secret = "ОченьЛичноеСлово"
    note = await mk_note(admin, secret)
    r = await admin.patch(
        f"{N}/{note['id']}", json={"text": secret + "2"}, headers=v(note["version"])
    )
    assert r.status_code == 200
    assert (await admin.delete(f"{N}/{note['id']}")).status_code == 204
    rows = await sql(
        "SELECT action, diff::text, label FROM audit_log WHERE entity = 'note' ORDER BY id"
    )
    assert [x[0] for x in rows] == ["note.create", "note.update", "note.delete"]
    assert all(secret not in (x[1] + (x[2] or "")) for x in rows)
    sentences = [i["text"] for i in (await admin.get(A, params={"entity": "note"})).json()["items"]]
    assert sorted(s.split(": ", 1)[1] for s in sentences) == [
        "добавлена заметка",
        "изменена заметка",
        "удалена заметка",
    ]
    # and the audit search cannot find the text either
    assert (await admin.get(A, params={"q": secret})).json()["items"] == []


# ---- 422s name their field, baseline of stock metrics, half-up rounding ----------------------


def fields_of(r: httpx.Response) -> list[str]:
    assert r.status_code == 422, r.text
    return [str(e["loc"][-1]) for e in r.json()["errors"]]


async def test_patch_null_on_a_required_field_is_422_with_the_field(
    admin: httpx.AsyncClient,
) -> None:
    goal = await mk_goal(admin)
    for field in ("title", "metric", "target", "start_date", "deadline"):
        r = await admin.patch(f"{G}/{goal['id']}", json={field: None}, headers=v(goal["version"]))
        assert fields_of(r) == [field], field
    # an all-branches goal may still be set by branch_id: null
    r = await admin.patch(f"{G}/{goal['id']}", json={"branch_id": None}, headers=v(goal["version"]))
    assert r.status_code == 200


async def test_every_goal_422_names_its_field(admin: httpx.AsyncClient) -> None:
    base = {
        "title": "t",
        "metric": "income",
        "target": 5,
        "start_date": "2027-01-01",
        "deadline": "2027-02-01",
    }
    cases = [
        ({"title": ""}, "title"),
        ({"title": "x" * 121}, "title"),
        ({"metric": "nope"}, "metric"),
        ({"target": 0}, "target"),
        ({"target": "abc"}, "target"),
        ({"deadline": "2027-01-01"}, "deadline"),
        ({"metric": "collection_rate_month", "target": 101}, "target"),
        ({"metric": "active_students", "target": 5, "baseline": 5}, "target"),
        ({"baseline": -1, "metric": "active_students"}, "baseline"),
        ({"start_date": None}, "start_date"),
    ]
    for change, field in cases:
        r = await admin.post(G, json={**base, **change})
        assert field in fields_of(r), (change, r.text)
    goal = await mk_goal(admin, metric="collection_rate_month", target=50)
    r = await admin.patch(f"{G}/{goal['id']}", json={"target": 150}, headers=v(goal["version"]))
    assert fields_of(r) == ["target"]
    r = await admin.patch(
        f"{G}/{goal['id']}", json={"deadline": "2000-01-01"}, headers=v(goal["version"])
    )
    assert (r.json()["code"], fields_of(r)) == ("goal_dates_invalid", ["deadline"])


async def test_stock_goal_takes_the_value_now_as_baseline_and_counts_from_it(
    admin: httpx.AsyncClient,
) -> None:
    await seed(admin)  # 3 active students
    goal = await mk_goal(admin, metric="active_students", target=6, **WINDOW)
    assert (goal["baseline"], goal["current"]) == (3, 3)
    assert goal["progress_pct"] == 0.0  # not 50 %: nothing has been gained yet
    # a cumulative metric always starts from 0, a sent baseline is ignored
    other = await mk_goal(admin, metric="income", baseline=7, **WINDOW)
    assert other["baseline"] == 0
    # the superadmin may set the start by hand, and the form can send it back empty = now
    r = await admin.patch(f"{G}/{goal['id']}", json={"baseline": 1}, headers=v(goal["version"]))
    assert r.json()["baseline"] == 1 and r.json()["progress_pct"] == 40.0  # (3-1)/(6-1)
    r = await admin.patch(
        f"{G}/{goal['id']}", json={"baseline": None}, headers=v(r.json()["version"])
    )
    assert r.json()["baseline"] == 3
    # moving to a flow metric drops the baseline, back to a stock metric takes the value now
    r = await admin.patch(
        f"{G}/{goal['id']}", json={"metric": "income"}, headers=v(r.json()["version"])
    )
    assert r.json()["baseline"] == 0
    r = await admin.patch(
        f"{G}/{goal['id']}", json={"metric": "active_students"}, headers=v(r.json()["version"])
    )
    assert r.json()["baseline"] == 3


@pytest.mark.parametrize(
    ("on", "current", "progress", "expected", "status"),
    [
        (START, 24, 0.0, 0.0, "по графику"),  # day 1: 24 of 48 with a baseline of 24 is 0 %
        (date(2027, 1, 6), 36, 50.0, 50.0, "по графику"),
        (date(2027, 1, 6), 35, 45.8, 50.0, "отстаём"),
        (END, 47, 95.8, 100.0, "отстаём"),
        (END, 48, 100.0, 100.0, "достигнута"),
        (date(2027, 1, 12), 40, 66.7, 100.0, "срок прошёл"),
    ],
)
def test_pace_of_a_stock_metric_counts_from_the_baseline(
    on: date, current: float, progress: float, expected: float, status: str
) -> None:
    r = pace("active_stu" + "dents", current, 48, START, END, on, baseline=24)
    assert (r["progress_pct"], r["expected_pct"], r["status"]) == (progress, expected, status)


def test_percentages_round_half_up() -> None:
    assert pace("income", 5625, 10000, START, END, START)["progress_pct"] == 56.3
    assert pace("income", 0, 10, START, END, date(2027, 1, 2))["expected_pct"] == 10.0
    # 1 day of 16 is 6.25 %: half up gives 6.3 (float round() would give 6.2)
    assert pace("income", 0, 10, START, date(2027, 1, 17), date(2027, 1, 2))["expected_pct"] == 6.3
