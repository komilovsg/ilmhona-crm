"""The enrollment day of a student added to a running cohort can be moved back to when they
really started: earlier lessons then take marks. Moving it later never drops marks, back-dating
shows the debt it adds, rights and scope are those of enrolling."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.audit.sentences import Entry, sentence
from app.cohorts.status import TZ, today
from tests.conftest import SignedIn, sql
from tests.edu import C, make_cohort, make_course, make_room
from tests.test_attendance import NEW, E, mark, past_cohort


async def _join_now(c: httpx.AsyncClient, cohort: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """A new student added today (enrolled_at = now): the earlier lessons are locked."""
    r = await c.post(f"{C}/{cohort['id']}/enrollments", json={**NEW, **extra})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def _move(
    c: httpx.AsyncClient, row: dict[str, Any], day: date, version: int | None = None
) -> httpx.Response:
    return await c.patch(
        f"{E}/{row['id']}/enrolled-on",
        json={"enrolled_on": day.isoformat()},
        headers={"X-Record-Version": str(row["version"] if version is None else version)},
    )


async def _last_sentence(action: str) -> str:
    row = (
        await sql(
            "SELECT a.action, a.entity, a.label, a.diff, u.full_name FROM audit_log a "
            "LEFT JOIN app_user u ON u.id = a.user_id WHERE a.action = :a ORDER BY a.id DESC",
            a=action,
        )
    )[0]
    return sentence(Entry(row[4], row[0], row[1], row[2], row[3]))


async def test_backdate_unlocks_earlier_lessons_and_is_audited(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)  # lessons t-9 .. t-1
    row = await _join_now(admin, cohort)
    r = await mark(admin, lessons[0], row["id"])
    assert (r.status_code, r.json()["code"]) == (422, "enrolled_after_lesson")
    assert r.json()["params"]["enrolled"] == today().strftime("%d.%m")
    # the lesson screen lists them as late, with what the move needs
    lesson = (await admin.get(f"/api/v1/lessons/{lessons[0]}/attendance")).json()
    assert [x["enrollment_id"] for x in lesson["late"]] == [row["id"]]
    assert lesson["late"][0]["enrolled_on"] == today().isoformat()
    assert lesson["total"] == 0

    day = today() - timedelta(days=9)
    r = await _move(admin, row, day)
    assert r.status_code == 200, r.text
    assert r.json()["enrolled_at"].startswith(day.isoformat())
    assert r.json()["version"] > row["version"]
    assert (await mark(admin, lessons[0], row["id"])).status_code == 200
    lesson = (await admin.get(f"/api/v1/lessons/{lessons[0]}/attendance")).json()
    assert lesson["late"] == [] and lesson["total"] == 1
    old, new = today().strftime("%d.%m"), day.strftime("%d.%m")
    assert f"изменена дата зачисления студента Новиков Нур в потоке {cohort['code']}" in (
        await _last_sentence("enrollment.date")
    )
    assert f"с {old} на {new}" in await _last_sentence("enrollment.date")


async def test_enroll_with_a_past_day_and_clamp_to_cohort_start(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    start = date.fromisoformat(cohort["start_date"])
    # added with the day they started
    row = await _join_now(admin, cohort, enrolled_on=(today() - timedelta(days=3)).isoformat())
    assert row["enrolled_at"].startswith((today() - timedelta(days=3)).isoformat())
    # before the cohort start: the start
    r = await _move(admin, row, start - timedelta(days=20))
    assert r.status_code == 200 and r.json()["enrolled_at"].startswith(start.isoformat())
    # after today: refused, on the field
    r = await _move(admin, r.json(), today() + timedelta(days=1))
    assert r.status_code == 422 and r.json()["code"] == "enrolled_on_future"
    assert r.json()["errors"][0]["loc"][-1] == "enrolled_on"
    r = await admin.post(
        f"{C}/{cohort['id']}/enrollments",
        json={**NEW, "enrolled_on": (today() + timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 422 and r.json()["code"] == "enrolled_on_future"


async def test_moving_later_is_refused_when_marks_exist_before(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    row = await _join_now(admin, cohort, enrolled_on=(today() - timedelta(days=9)).isoformat())
    assert (await mark(admin, lessons[2], row["id"])).status_code == 200  # t-7
    r = await _move(admin, row, today() - timedelta(days=5))
    assert (r.status_code, r.json()["code"]) == (422, "enrolled_on_has_marks")
    assert r.json()["params"]["first_mark"] == (today() - timedelta(days=7)).isoformat()
    assert len(await sql("SELECT 1 FROM attendance WHERE enrollment_id = :e", e=row["id"])) == 1
    # later, but not past the mark: fine
    r = await _move(admin, row, today() - timedelta(days=7))
    assert r.status_code == 200, r.text


async def test_stale_version_is_a_conflict(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    row = await _join_now(admin, cohort)
    assert (await _move(admin, row, today() - timedelta(days=2))).status_code == 200
    r = await _move(admin, row, today() - timedelta(days=4))  # the version it loaded is old
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    r = await admin.patch(
        f"{E}/{row['id']}/enrolled-on", json={"enrolled_on": today().isoformat()}, no_version=True
    )
    assert r.status_code == 428


async def test_scope_and_rights_follow_enrolling(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    own, _ = await past_cohort(admin, name="A", instructor_id=me)
    other, _ = await past_cohort(admin, name="B")
    mine = await _join_now(admin, own)  # a row a manager added: still in the instructor's cohort
    theirs = await _join_now(admin, other)
    day = today() - timedelta(days=5)
    assert (await _move(ins, mine, day)).status_code == 403  # only admin and manager move it
    assert (await _move(ins, theirs, day)).status_code == 403
    assert (
        await ins.get(f"{E}/{theirs['id']}/enrolled-on", params={"enrolled_on": str(day)})
    ).status_code == 403
    # another branch's manager: 404; a role without cohorts change: 403
    far = await login_as("far", "manager", branch="Истаравшан")
    assert (await _move(far, theirs, day)).status_code == 404
    viewer = await login_as("v", await _viewer_role(), branch="Душанбе")
    assert (await _move(viewer, theirs, day)).status_code == 403


async def _viewer_role() -> Any:
    from tests.conftest import make_role

    return await make_role("Только просмотр", {"cohorts": "view", "attendance": "change"})


def _months(a: date, b: date) -> int:
    return (b.year * 12 + b.month) - (a.year * 12 + a.month) + 1


async def test_backdating_shows_the_debt_change(admin: httpx.AsyncClient) -> None:
    start = today() - timedelta(days=70)
    cohort = await make_cohort(
        admin,
        await make_course("Курс Д"),
        await make_room(name="R-D"),
        start=start,
        weeks=20,
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        price_month="500",
    )
    row = await _join_now(admin, cohort)
    p = await admin.get(f"{E}/{row['id']}/enrolled-on", params={"enrolled_on": str(start)})
    assert p.status_code == 200, p.text
    before, after = Decimal("500"), Decimal(500 * _months(start, today()))
    assert p.json()["enrolled_on"] == str(start)
    assert {k: Decimal(v) for k, v in p.json()["debt"].items()} == {
        "before": before,
        "after": after,
    }
    r = await _move(admin, row, start)
    assert {k: Decimal(v) for k, v in r.json()["debt"].items()} == {
        "before": before,
        "after": after,
    }
    money = (await admin.get(f"/api/v1/payments/by-cohort/{cohort['id']}")).json()["items"]
    assert [Decimal(m["debt"]) for m in money] == [after]


async def test_free_cohort_has_no_debt_change(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin, funding="бесплатный", price_month="0")
    row = await _join_now(admin, cohort)
    r = await _move(admin, row, today() - timedelta(days=5))
    assert r.status_code == 200 and r.json()["debt"] is None


async def test_instructor_cannot_move_the_day_manager_can(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins2", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    own, _ = await past_cohort(admin, name="A", instructor_id=me)
    row = await _join_now(admin, own)
    day = today() - timedelta(days=5)
    assert (await _move(ins, row, day)).status_code == 403
    r = await ins.get(f"{E}/{row['id']}/enrolled-on", params={"enrolled_on": str(day)})
    assert r.status_code == 403
    # back-dating while enrolling (the journal flow) is closed to them too
    r = await ins.post(f"{C}/{own['id']}/enrollments", json={**NEW, "enrolled_on": str(day)})
    assert r.status_code == 403
    mgr = await login_as("mgr2", "manager", branch="Душанбе")
    assert (await _move(mgr, row, day)).status_code == 200


def _day(row: dict[str, Any]) -> date:
    return datetime.fromisoformat(row["enrolled_at"]).astimezone(TZ).date()


async def test_bulk_date_updates_all_selected(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    rows = []
    for i in range(3):
        r = await admin.post(
            f"{C}/{cohort['id']}/enrollments",
            json={"new_student": {"full_name": f"Студент {i}", "phone": f"+99290000010{i}"}},
        )
        assert r.status_code == 201, r.text
        rows.append(r.json())
    day = today() - timedelta(days=4)
    r = await admin.post(
        f"{C}/{cohort['id']}/enrollments/enrolled-date",
        json={"enrollment_ids": [x["id"] for x in rows], "enrolled_on": day.isoformat()},
    )
    assert (r.status_code, r.json()) == (200, {"updated": 3}), r.text
    got = (await admin.get(f"{C}/{cohort['id']}/enrollments")).json()
    assert [_day(x) for x in got] == [day] * 3
    assert len(await sql("SELECT 1 FROM audit_log WHERE action = 'enrollment.date'")) == 3


async def test_bulk_date_forbidden_for_instructor(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins3", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    own, _ = await past_cohort(admin, name="A", instructor_id=me)
    row = await _join_now(admin, own)
    r = await ins.post(
        f"{C}/{own['id']}/enrollments/enrolled-date",
        json={"enrollment_ids": [row["id"]], "enrolled_on": today().isoformat()},
    )
    assert r.status_code == 403


async def test_bulk_date_foreign_id_changes_nothing(admin: httpx.AsyncClient) -> None:
    a, _ = await past_cohort(admin, name="A")
    b, _ = await past_cohort(admin, name="B")
    mine = await _join_now(admin, a)
    theirs = await _join_now(admin, b)
    day = today() - timedelta(days=3)
    r = await admin.post(
        f"{C}/{a['id']}/enrollments/enrolled-date",
        json={"enrollment_ids": [mine["id"], theirs["id"]], "enrolled_on": day.isoformat()},
    )
    assert r.status_code == 404
    for c in (a, b):
        rows = (await admin.get(f"{C}/{c['id']}/enrollments")).json()
        assert all(_day(x) == today() for x in rows)
    future = (today() + timedelta(days=1)).isoformat()
    r = await admin.post(
        f"{C}/{a['id']}/enrollments/enrolled-date",
        json={"enrollment_ids": [mine["id"]], "enrolled_on": future},
    )
    assert r.status_code == 422
