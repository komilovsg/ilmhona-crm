"""Audit log v2: every entry is a Russian sentence; failed logins and lockouts are logged;
filters, paging, links."""

import httpx

from app.audit.sentences import Entry, sentence
from tests.conftest import PASSWORD, SignedIn, make_role, sql
from tests.edu import make_cohort, make_course, make_room, make_student

A = "/api/v1/audit"


async def _texts(c: httpx.AsyncClient, **params: str) -> list[str]:
    r = await c.get(A, params=params)
    assert r.status_code == 200, r.text
    return [i["text"] for i in r.json()["items"]]


def test_sentences_read_like_russian() -> None:
    e = Entry(
        "Курбон",
        "student.update",
        "student",
        "Алиев Алишер",
        {"phone": ["+992900000001", "+992930000002"]},
    )
    assert (
        sentence(e)
        == "Курбон: изменён студент Алиев Алишер — телефон +992900000001 → +992930000002"
    )
    assert (
        sentence(Entry("Курбон", "cohort.create", "cohort", "G-012", {}))
        == "Курбон: создан поток G-012"
    )
    assert (
        sentence(Entry("Курбон", "auth.login", "app_user", "Курбон", {}))
        == "Курбон — вход в систему"
    )
    assert (
        sentence(Entry(None, "auth.login_failed", "login", "ali", {}))
        == "Неудачная попытка входа для логина ali"
    )
    locked = Entry(None, "auth.locked", "login", "ali", {"minutes": [None, 15]})
    assert sentence(locked) == "Логин ali заблокирован на 15 минут"
    many = {f: ["a", "b"] for f in ("phone", "email", "full_name", "gender", "direction")}
    assert sentence(Entry("К", "student.update", "student", "X", many)).endswith("и ещё 1")


async def test_entries_of_the_app_read_as_sentences(admin: httpx.AsyncClient) -> None:
    room, course = await make_room(), await make_course("Python")
    cohort = await make_cohort(admin, course, room)
    sid = await make_student("Алиев Алишер", phone="+992900000001")
    await admin.patch(f"/api/v1/students/{sid}", json={"phone": "+992930000002"})
    await admin.post(f"/api/v1/cohorts/{cohort['id']}/enrollments", json={"student_id": str(sid)})
    texts = await _texts(admin)
    assert (
        "User root: изменён студент Алиев Алишер — телефон +992900000001 → +992930000002" in texts
    )
    assert f"User root: создан поток {cohort['code']}" in texts
    assert f"User root: зачислен студент Алиев Алишер в поток {cohort['code']}" in texts
    await admin.post(f"/api/v1/cohorts/{cohort['id']}/cancel")
    gone = await make_student("Удалённый Студент")
    assert (await admin.delete(f"/api/v1/students/{gone}")).status_code == 204
    texts = await _texts(admin)
    assert f"User root: отменён поток {cohort['code']}" in texts
    # a deleted row keeps its name in the log
    assert "User root: удалён студент Удалённый Студент" in texts


async def test_failed_logins_and_lockout_are_logged_without_the_password(
    client: httpx.AsyncClient, admin: httpx.AsyncClient
) -> None:
    secret = "Sup3r-secret-guess!"
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"login": "ghost", "password": secret})
        assert r.status_code == 401
    texts = await _texts(admin)
    assert texts.count("Неудачная попытка входа для логина ghost") == 5
    assert "Логин ghost заблокирован на 15 минут" in texts
    assert "User root — вход в систему" in texts
    assert secret not in str(await sql("SELECT diff::text, label, entity_id FROM audit_log"))
    # a locked login is refused before it is counted: no extra entry
    await client.post("/api/v1/auth/login", json={"login": "ghost", "password": secret})
    assert (await _texts(admin)).count("Неудачная попытка входа для логина ghost") == 5


async def test_filters_period_section_branch_user_action_text_and_paging(
    admin: httpx.AsyncClient,
) -> None:
    room, course = await make_room(), await make_course("Python")
    await make_cohort(admin, course, room)
    sid = await make_student("Алиев Алишер")
    await admin.patch(f"/api/v1/students/{sid}", json={"phone": "+992900000001"})
    root = (await admin.get("/api/v1/auth/me")).json()["id"]

    assert all("студент" in t for t in await _texts(admin, section="students"))
    assert any("поток" in t for t in await _texts(admin, section="cohorts"))
    assert await _texts(admin, section="cohorts", user_id=root, action="student.update") == []
    assert any("вход в систему" in t for t in await _texts(admin, section="auth"))
    assert await _texts(admin, q="Алиев") and not await _texts(admin, q="нет-такого")
    assert await _texts(admin, q="+992900000001")  # searches the changed values too
    assert await _texts(admin, date_from="2020-01-01", date_to="2099-01-01")
    assert await _texts(admin, date_from="2099-01-01") == []
    assert await _texts(admin, date_to="2020-01-01") == []
    one = (await admin.get(A, params={"page_size": "1"})).json()
    assert len(one["items"]) == 1 and one["total"] > 1
    branch = (await sql("SELECT id FROM branch WHERE name = 'Истаравшан'"))[0][0]
    assert await _texts(admin, branch_id=str(branch)) == []  # nothing there yet


async def test_links_point_to_existing_entities_in_scope(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    room, course = await make_room(), await make_course("Python")
    cohort = await make_cohort(admin, course, room)
    sid = await make_student("Алиев Алишер")
    await admin.patch(f"/api/v1/students/{sid}", json={"phone": "+992900000001"})
    items = (await admin.get(A, params={"action": "student.update"})).json()["items"]
    assert items[0]["link"] == {"entity": "student", "id": str(sid)}
    items = (await admin.get(A, params={"action": "cohort.create"})).json()["items"]
    assert items[0]["link"] == {"entity": "cohort", "id": cohort["id"]}
    login = (await admin.get(A, params={"action": "auth.login"})).json()["items"]
    assert login[0]["link"] == {"entity": "app_user", "id": login[0]["entity_id"]}
    await admin.delete(f"/api/v1/students/{sid}")
    for i in (await admin.get(A, params={"entity": "student"})).json()["items"]:
        assert i["link"] is None  # the student is gone
    # a reader without the students section gets no student link
    viewer = await login_as("viewer", await make_role("Только журнал", {"audit": "view"}))
    for i in (await viewer.get(A)).json()["items"]:
        assert i["link"] is None


async def test_branch_bound_reader_sees_only_their_branch_and_no_login_noise(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    role = await make_role("Менеджер ЦО", {"students": "change", "audit": "view"})
    mgr = await login_as("dush", role, branch="Душанбе")
    istar_mgr = await login_as("istar", role, branch="Истаравшан")
    await make_student("Душанбинец", branch="Душанбе")
    ds = (await sql("SELECT id FROM student WHERE full_name = 'Душанбинец'"))[0][0]
    is_ = await make_student("Истаравшанец", branch="Истаравшан")
    await mgr.patch(f"/api/v1/students/{ds}", json={"phone": "+992900000001"})
    await istar_mgr.patch(f"/api/v1/students/{is_}", json={"phone": "+992900000002"})
    await admin.post("/api/v1/auth/login", json={"login": "ghost", "password": PASSWORD})
    mine = await _texts(mgr)
    assert any("Душанбинец" in t for t in mine)
    assert not any("Истаравшанец" in t for t in mine)
    assert not any("ghost" in t for t in mine)  # entries without a branch stay with the superadmin
    everything = await _texts(admin)
    assert any("Истаравшанец" in t for t in everything) and any("ghost" in t for t in everything)


def test_sentences_are_gender_neutral() -> None:
    """No «вошёл / изменил / создал» for a woman, no «Система создал»."""
    for who in ("Каримова Мадина", None):
        for action, entity, label in (
            ("student.create", "student", "Алиев Алишер"),
            ("student.update", "student", "Алиев Алишер"),
            ("room.create", "room", "Lovelace"),
            ("role.delete", "role", "Помощник"),
            ("cohort.cancel", "cohort", "G-001"),
            ("auth.login", "app_user", "x"),
            ("auth.change_password", "app_user", "x"),
            ("profile.update", "app_user", "x"),
            ("enrollment.create", "enrollment", None),
        ):
            diff = {"student": [None, "A"], "cohort": [None, "G"]} if "enrollment" in action else {}
            text = sentence(Entry(who, action, entity, label, diff))
            assert text.startswith(who or "Система"), text
            for bad in ("вошёл", "вошла", "изменил", "создал", "удалил", "сменил", "зачислил"):
                assert bad not in text, text
    login = Entry("Каримова Мадина", "auth.login", "app_user", "x", {})
    assert sentence(login) == "Каримова Мадина — вход в систему"
    assert (
        sentence(Entry(None, "cohort.create", "cohort", "G-012", {}))
        == "Система: создан поток G-012"
    )


def test_money_reads_the_same_everywhere() -> None:
    e = Entry("К", "cohort.update", "cohort", "G-1", {"price_month": ["500.00", "650.00"]})
    assert sentence(e).endswith("цена в месяц 500 → 650 TJS")
    diff = {"default_price_month": ["500.00", "650.50"]}
    assert sentence(Entry("К", "course.update", "course", "Python", diff)).endswith(
        "500 → 650.50 TJS"
    )


def test_export_sentence() -> None:
    diff = {"rows": 3, "filters": {"q": "али", "status": "активный"}}
    e = Entry("Каримова Мадина", "export", "student", None, diff)
    assert sentence(e) == (
        "Каримова Мадина — выгрузка в Excel: студенты, 3 строки (фильтры: поиск али, статус активный)"
    )
    plain = Entry(None, "export", "audit_log", None, {"rows": 21, "filters": {}})
    assert sentence(plain) == "Система — выгрузка в Excel: журнал, 21 строка"
