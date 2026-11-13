"""Grading schemes (owner decisions 2026-11-14): the academy standard, a cohort's own scheme,
scores per category, projected totals, the graduation recalculation, the Excel round trip."""

import io
import zipfile
from datetime import timedelta
from typing import Any

import httpx
import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy.exc import IntegrityError

from app.cohorts.status import today
from app.metrics import grading as g
from tests.conftest import SignedIn, make_role, sql
from tests.edu import make_cohort, make_course, make_room
from tests.money import enroll as money_enroll
from tests.reports import finish
from tests.test_attendance import enroll, mark, past_cohort

S = "/api/v1/grading/standard"
C = "/api/v1/cohorts"
E = "/api/v1/enrollments"

DEFAULT = [
    {"key": "attendance", "name": "Посещаемость", "weight": 20, "kind": "attendance"},
    {"key": "homework", "name": "Домашние задания", "weight": 40, "kind": "manual"},
    {"key": "final", "name": "Финал", "weight": 40, "kind": "manual"},
]
WITH_PROJECT = [
    {"key": "attendance", "name": "Посещаемость", "weight": 20, "kind": "attendance"},
    {"key": "homework", "name": "Домашние задания", "weight": 30, "kind": "manual"},
    {"key": "final", "name": "Финал", "weight": 30, "kind": "manual"},
    {"name": "Проект", "weight": 20, "kind": "manual"},
]


def cats(*weights: tuple[str, int, str]) -> list[dict[str, Any]]:
    return [{"name": n, "weight": w, "kind": k} for n, w, k in weights]


async def scores(c: httpx.AsyncClient, enrollment: str, **values: int | None) -> httpx.Response:
    return await c.patch(f"{E}/{enrollment}/grade", json={"scores": values})


async def audit_texts(c: httpx.AsyncClient, action: str) -> list[str]:
    r = await c.get("/api/v1/audit", params={"action": action})
    return [i["text"] for i in r.json()["items"]]


# ---- the scheme rules --------------------------------------------------------------------


async def test_default_standard_is_attendance_20_homework_40_final_40_pass_70(
    login_as: SignedIn,
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")  # everybody reads the standard
    r = await ins.get(S)
    assert r.status_code == 200
    body = r.json()
    assert body["scheme"]["categories"] == DEFAULT
    assert (body["scheme"]["pass_score"], body["can_edit"]) == (70, False)
    assert (
        body["scheme"]["target_retention"],
        body["scheme"]["target_attendance"],
        body["scheme"]["target_pass_rate"],
    ) == (85, 80, 70)


async def test_weights_sum_exactly_100_enforced_by_api_and_db(admin: httpx.AsyncClient) -> None:
    for bad, expect in (
        (cats(("Посещаемость", 20, "attendance"), ("ДЗ", 70, "manual")), "Сумма баллов 90"),
        (cats(("Посещаемость", 20, "attendance"), ("ДЗ", 90, "manual")), "Сумма баллов 110"),
        (cats(("ДЗ", 100, "manual")), "ровно одна, сейчас 0"),
        (
            cats(("П", 10, "attendance"), ("Q", 10, "attendance"), ("ДЗ", 80, "manual")),
            "ровно одна, сейчас 2",
        ),
        (
            cats(("Посещаемость", 50, "attendance"), ("ДЗ", 50, "manual"), ("дз", 0, "manual")),
            "повторяется",
        ),
        (cats(("Посещаемость", 100, "attendance"), ("Пусто", 0, "manual")), "баллов от 1"),
    ):
        r = await admin.patch(S, json={"categories": bad})
        assert (r.status_code, r.json()["code"]) == (422, "grading_scheme_invalid"), bad
        assert any(expect in p for p in r.json()["params"]["problems"]), r.json()
    assert (await admin.patch(S, json={"pass_score": 101})).status_code == 422
    # attendance may weigh 0..100
    ok = cats(("Посещаемость", 0, "attendance"), ("ДЗ", 100, "manual"))
    assert (await admin.patch(S, json={"categories": ok})).status_code == 200
    # the database refuses a scheme that does not sum to 100 or loses its attendance category
    with pytest.raises(IntegrityError, match="sums to 90 points, not 100"):
        await sql("UPDATE grading_category SET weight = 90 WHERE kind = 'manual'")
    with pytest.raises(IntegrityError, match="has 0 attendance categories"):
        await sql("DELETE FROM grading_category WHERE kind = 'attendance'")  # weighs 0 here
    assert (await sql("SELECT sum(weight) FROM grading_category"))[0][0] == 100


async def test_standard_only_superadmin_changes_it(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    mgr = await login_as("mgr", "manager")
    ins = await login_as("ins", "instructor", branch="Душанбе")
    helper = await login_as(
        "adm", await make_role("Администратор", {"cohorts": "change", "attendance": "change"})
    )
    for c in (mgr, ins, helper):
        r = await c.patch(S, json={"pass_score": 60})
        assert r.status_code == 403
        assert (await c.post(f"{S}/import", content=b"x")).status_code == 403
        assert (await c.get(S)).status_code == 200
    r = await admin.patch(S, json={"pass_score": 60, "target_retention": 90})
    assert r.status_code == 200 and r.json()["scheme"]["pass_score"] == 60
    texts = await audit_texts(admin, "grading.standard_update")
    assert texts == [
        "User root: изменён стандарт оценок академии — проходной балл 70 → 60; "
        "цель по удержанию, % 85 → 90"
    ]


async def test_standard_version_check(admin: httpx.AsyncClient) -> None:
    v = (await admin.get(S)).json()["version"]
    assert (
        await admin.patch(S, json={"pass_score": 65}, headers={"X-Record-Version": str(v)})
    ).status_code == 200
    r = await admin.patch(S, json={"pass_score": 60}, headers={"X-Record-Version": str(v)})
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    assert r.json()["params"]["current"]["scheme"]["pass_score"] == 65
    assert (await admin.patch(S, json={"pass_score": 60}, no_version=True)).status_code == 428


# ---- per-cohort override -----------------------------------------------------------------


async def test_override_inherits_until_changed_then_reset_returns_the_standard(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, lessons = await past_cohort(admin, instructor_id=me)
    url = f"{C}/{cohort['id']}/grading"
    got = (await ins.get(url)).json()
    assert (got["source"], got["version"], got["can_edit"]) == ("standard", 0, True)
    # the standard changes: the inheriting cohort follows
    await admin.patch(S, json={"pass_score": 65})
    assert (await ins.get(url)).json()["scheme"]["pass_score"] == 65
    # the instructor adds «Проект · 20» to their cohort, the weights rebalanced to 100
    r = await ins.patch(url, json={"categories": WITH_PROJECT})
    assert r.status_code == 200, r.text
    own = r.json()
    assert own["source"] == "cohort" and own["version"] >= 1
    names = [(c["name"], c["weight"]) for c in own["scheme"]["categories"]]
    assert names == [("Посещаемость", 20), ("Домашние задания", 30), ("Финал", 30), ("Проект", 20)]
    project = own["scheme"]["categories"][3]["key"]
    assert project not in ("homework", "final", "attendance")
    # the standard changes again: the cohort keeps its own scheme
    await admin.patch(S, json={"pass_score": 50})
    assert (await ins.get(url)).json()["scheme"]["pass_score"] == 65
    # scores: one column per manual category, 0..weight
    e = await enroll(admin, cohort, "Алиев")
    for lesson in lessons:
        await mark(admin, lesson, e)
    r = await scores(ins, e, homework=30, final=30, **{project: 20})
    assert r.status_code == 200 and r.json()["total"] == 100
    r = await scores(ins, e, **{project: 21})
    assert r.status_code == 422
    assert r.json()["errors"][0]["ctx"] == {"le": 20}
    grades = (await ins.get(f"{C}/{cohort['id']}/grades")).json()
    assert [c["key"] for c in grades["scheme"]["categories"]][-1] == project
    # «Вернуть стандарт академии»: «Проект» has a score, so it needs a confirmation
    v = str((await ins.get(url)).json()["version"])
    r = await ins.delete(url, headers={"X-Record-Version": v})
    assert (r.status_code, r.json()["code"]) == (409, "grading_scores_archived")
    assert r.json()["params"]["categories"] == [{"name": "Проект", "scores": 1}]
    r = await ins.delete(url, params={"confirm_archive": "true"}, headers={"X-Record-Version": v})
    assert r.status_code == 200
    back = r.json()
    assert back["source"] == "standard" and back["scheme"]["pass_score"] == 50
    assert back["archived"] == [{"key": project, "name": "Проект", "scores": 1}]
    # the score is kept, only not counted: 20 + 30 + 30 on the standard
    assert (await sql("SELECT count(*) FROM grade_score WHERE category_key = :k", k=project))[0][
        0
    ] == 1
    row = (await ins.get(f"{C}/{cohort['id']}/grades")).json()["rows"][0]
    assert row["total"] == 80 and row["scores"][project] == 20
    texts = await audit_texts(admin, "grading.cohort_update")
    assert texts[0] == (
        f"User ins: изменена шкала оценок потока {cohort['code']} — баллы Посещаемость 20, "
        "Домашние задания 40, Финал 40 → Посещаемость 20, Домашние задания 30, Финал 30, Проект 20"
    )
    reset = (await audit_texts(admin, "grading.cohort_reset"))[0]
    assert reset.startswith(f"User ins: потоку {cohort['code']} возвращён стандарт оценок академии")
    assert reset.endswith("оценки сохранены в архиве: Проект (1)")


async def test_removing_a_category_with_scores_needs_confirmation_and_keeps_the_scores(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    await scores(admin, e, homework=35, final=30)
    url = f"{C}/{cohort['id']}/grading"
    no_final = cats(("Посещаемость", 20, "attendance"), ("Домашние задания", 80, "manual"))
    r = await admin.patch(url, json={"categories": no_final})
    assert (r.status_code, r.json()["code"]) == (409, "grading_scores_archived")
    assert r.json()["params"]["categories"] == [{"name": "Финал", "scores": 1}]
    assert (await admin.get(url)).json()["source"] == "standard"  # nothing written
    r = await admin.patch(url, json={"categories": no_final, "confirm_archive": True})
    assert r.status_code == 200
    assert r.json()["archived"] == [{"key": "final", "name": "Финал", "scores": 1}]
    assert (await admin.get(f"{C}/{cohort['id']}/grades")).json()["rows"][0]["total"] == 35
    # the same name back: the old key, the old scores count again
    r = await admin.patch(
        url,
        json={
            "categories": DEFAULT[:1]
            + cats(("Домашние задания", 40, "manual"), ("финал", 40, "manual"))
        },
    )
    assert r.status_code == 200 and r.json()["archived"] == []
    assert r.json()["scheme"]["categories"][2]["key"] == "final"
    assert (await admin.get(f"{C}/{cohort['id']}/grades")).json()["rows"][0]["total"] == 65


async def test_cohort_scheme_version_check(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    cohort, _ = await past_cohort(admin)
    url = f"{C}/{cohort['id']}/grading"
    r = await admin.patch(url, json={"pass_score": 60}, headers={"X-Record-Version": "0"})
    assert r.status_code == 200
    v = r.json()["version"]
    r = await admin.patch(url, json={"pass_score": 50}, headers={"X-Record-Version": "0"})
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    assert r.json()["params"]["current"]["scheme"]["pass_score"] == 60
    r = await admin.patch(url, json={"pass_score": 50}, headers={"X-Record-Version": str(v)})
    assert r.status_code == 200 and r.json()["version"] > v


async def test_permissions_matrix_for_override_scores_recalc_and_import(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    mine, _ = await past_cohort(admin, name="A", instructor_id=me)
    other, _ = await past_cohort(admin, name="B")
    far = await make_cohort(
        admin,
        await make_course("Курс F"),
        await make_room("Истаравшан", "R-F"),
        branch="Истаравшан",
        start=today() - timedelta(days=9),
        weeks=2,
    )
    mgr = await login_as("mgr", "manager", branch="Душанбе")
    viewer = await login_as(
        "adm", await make_role("Администратор", {"cohorts": "view", "attendance": "view"})
    )
    e = {c["id"]: await enroll(admin, c, f"Студент {c['code']}") for c in (mine, other)}
    e[far["id"]] = await money_enroll(admin, far, "Дальний", branch="Истаравшан")
    file = template_bytes(DEFAULT)

    async def calls(c: httpx.AsyncClient, cohort: dict[str, Any]) -> list[int]:
        url = f"{C}/{cohort['id']}/grading"
        return [
            (await c.get(url)).status_code,
            (await c.patch(url, json={"pass_score": 61})).status_code,
            (await scores(c, e[cohort["id"]], homework=1)).status_code,
            (await c.post(f"{C}/{cohort['id']}/graduation-recalc")).status_code,
            (await c.post(f"{url}/import", content=file)).status_code,
            (await c.get(f"{C}/{cohort['id']}/graduation-preview")).status_code,
        ]

    # 409 on recalc = allowed but the cohort is not finished yet
    allowed = [200, 200, 200, 409, 200, 200]
    assert await calls(admin, far) == allowed
    assert await calls(mgr, other) == allowed  # own branch
    assert await calls(mgr, far) == [404] * 6  # another branch looks like nothing
    assert await calls(ins, mine) == allowed
    assert await calls(ins, other) == [404] * 6
    assert await calls(viewer, other) == [200, 403, 403, 403, 403, 200]


# ---- totals ------------------------------------------------------------------------------


def test_projected_is_the_total_scaled_from_the_categories_that_count_already() -> None:
    scheme = g.Scheme(
        id=None,  # type: ignore[arg-type]
        cohort_id=None,
        version=1,
        categories=(
            g.Category("attendance", "Посещаемость", 20, "attendance"),
            g.Category("homework", "ДЗ", 40, "manual"),
            g.Category("final", "Финал", 40, "manual"),
        ),
        pass_score=70,
        target_retention=85,
        target_attendance=80,
        target_pass_rate=70,
    )
    nothing = g.result(scheme, 0, 0, {})
    assert (nothing["total"], nothing["projected"], nothing["passed"]) == (0, None, False)
    # 9 of 10 lessons (18 of 20) and homework 30 of 40: 48 of 60 counted -> 80 of 100
    r = g.result(scheme, 9, 10, {"homework": 30})
    assert (r["total"], r["projected"], r["passed"]) == (48, 80, False)
    # every category in: projected = total
    r = g.result(scheme, 10, 10, {"homework": 40, "final": 10})
    assert (r["total"], r["projected"], r["passed"]) == (70, 70, True)
    # attendance not held yet, only the final: 30 of 40 -> 75
    assert g.result(scheme, 0, 0, {"final": 30})["projected"] == 75
    # a score above a lowered weight counts as the weight; an archived key does not count
    r = g.result(scheme, 0, 0, {"homework": 40, "old": 50})
    assert (r["points"], r["total"]) == ({"attendance": 0, "homework": 40, "final": 0}, 40)
    # 2 of 3 lessons of a 30-point attendance (20) and nothing else entered: 20 of 30 -> 67
    other = g.Scheme(
        **{
            **scheme.__dict__,
            "categories": (
                g.Category("attendance", "П", 30, "attendance"),
                g.Category("x", "X", 70, "manual"),
            ),
        }
    )
    assert g.result(other, 2, 3, {})["projected"] == 67
    assert g.scaled_points(30, 1, 4) == 8  # 7.5 rounds up


async def test_projected_and_pass_on_the_grades_tab(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    for lesson in lessons:
        await mark(admin, lesson, e)
    r = await scores(admin, e, homework=30)
    assert (r.json()["total"], r.json()["projected"], r.json()["passed"]) == (50, 83, False)
    await admin.patch(f"{C}/{cohort['id']}/grading", json={"pass_score": 50})
    row = (await admin.get(f"{C}/{cohort['id']}/grades")).json()["rows"][0]
    assert row["passed"] is True


# ---- graduation safety -------------------------------------------------------------------


async def finished(admin: httpx.AsyncClient) -> tuple[dict[str, Any], dict[str, str]]:
    cohort = await past_cohort_running(admin)
    ids = {
        n: await enroll(admin, cohort, n) for n in ("Сильный", "Пограничный", "Слабый", "Ручной")
    }
    await scores(admin, ids["Сильный"], homework=40, final=40)  # 80
    await scores(admin, ids["Пограничный"], homework=35, final=35)  # 70
    await scores(admin, ids["Слабый"], homework=20, final=20)  # 40
    await scores(admin, ids["Ручной"], homework=35, final=35)  # 70
    await finish(cohort)
    return cohort, ids


async def past_cohort_running(admin: httpx.AsyncClient) -> dict[str, Any]:
    return await make_cohort(
        admin,
        await make_course("Курс G"),
        await make_room(name="R-G"),
        start=today() - timedelta(days=20),
        weeks=8,
    )


async def status_of(ids: dict[str, str]) -> dict[str, str]:
    rows = await sql("SELECT id, status FROM enrollment")
    by_id = {str(i): s for i, s in rows}
    return {n: by_id[i] for n, i in ids.items()}


async def test_completed_cohort_scheme_change_flips_no_status_until_recalc(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, ids = await finished(admin)
    first = await status_of(ids)
    assert first == {
        "Сильный": "выпускник",
        "Пограничный": "выпускник",
        "Слабый": "завершил",
        "Ручной": "выпускник",
    }
    await sql("UPDATE enrollment SET status_manual = true WHERE id = :i", i=ids["Ручной"])
    url = f"{C}/{cohort['id']}/grading"
    r = await admin.patch(url, json={"pass_score": 75})
    assert r.status_code == 200
    assert await status_of(ids) == first  # totals moved, statuses did not
    preview = (await admin.get(f"{C}/{cohort['id']}/graduation-preview")).json()
    assert preview["completed"] is True
    assert [(c["student_name"], c["status"], c["new_status"]) for c in preview["changes"]] == [
        ("Пограничный", "выпускник", "завершил")
    ]
    assert [(c["student_name"], c["reason"]) for c in preview["skipped"]] == [
        ("Ручной", "статус задан вручную")
    ]
    # the totals moved the other way meanwhile: the recalc refuses a stale preview
    stale = await admin.post(f"{C}/{cohort['id']}/graduation-recalc", params={"expected": 2})
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    r = await admin.post(f"{C}/{cohort['id']}/graduation-recalc", params={"expected": 1})
    assert r.status_code == 200
    assert r.json()["changes"] == preview["changes"]  # what the preview said is what happened
    after = await status_of(ids)
    assert after == {**first, "Пограничный": "завершил"}
    assert (await admin.get(f"{C}/{cohort['id']}/graduation-preview")).json()["changes"] == []
    texts = await audit_texts(admin, "enrollment.update")
    assert any(
        t.startswith("User root: изменено зачисление студента Пограничный")
        and "статус выпускник → завершил" in t
        and "пересчёт по шкале оценок" in t
        for t in texts
    ), texts
    # lowering the bar: the weak one would become a graduate
    await admin.patch(url, json={"pass_score": 40})
    preview = (await admin.get(f"{C}/{cohort['id']}/graduation-preview")).json()
    assert {(c["student_name"], c["new_status"]) for c in preview["changes"]} == {
        ("Пограничный", "выпускник"),
        ("Слабый", "выпускник"),
    }
    assert preview["graduates"] == 2


async def test_graduates_count_master_list_dashboard_follow_statuses_not_the_scheme(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await finished(admin)

    async def numbers() -> tuple[Any, ...]:
        grads = (await admin.get("/api/v1/graduates/students")).json()
        ml = (await admin.get("/api/v1/master-list")).json()["items"]
        dash = (await admin.get("/api/v1/dashboard/overview")).json()
        return grads["total"], [m["graduates"] for m in ml], dash["graduates"]

    before = await numbers()
    assert before[0] == 3
    await admin.patch(f"{C}/{cohort['id']}/grading", json={"pass_score": 90})
    assert await numbers() == before
    await admin.post(f"{C}/{cohort['id']}/graduation-recalc")
    assert (await numbers())[0] == 0


async def test_closing_a_cohort_uses_its_own_pass_score(admin: httpx.AsyncClient) -> None:
    cohort = await past_cohort_running(admin)
    e = await enroll(admin, cohort, "Алиев")
    await scores(admin, e, homework=30, final=30)  # 60 without attendance
    await admin.patch(f"{C}/{cohort['id']}/grading", json={"pass_score": 60})
    await finish(cohort)
    assert (await sql("SELECT status FROM enrollment"))[0][0] == "выпускник"


# ---- Excel -------------------------------------------------------------------------------


def template_bytes(categories: list[dict[str, Any]], extra: list[list[Any]] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Категория", "Баллы", "Тип"])
    for c in categories:
        ws.append([c["name"], c["weight"], "авто" if c["kind"] == "attendance" else "вручную"])
    for row in extra or []:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_excel_template_round_trip(admin: httpx.AsyncClient) -> None:
    await admin.patch(
        S, json={"categories": WITH_PROJECT, "pass_score": 65, "target_attendance": 75}
    )
    r = await admin.get(f"{S}/template")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = [tuple(c.value for c in row) for row in ws.iter_rows()]
    assert rows == [
        ("Категория", "Баллы", "Тип"),
        ("Посещаемость", 20, "авто"),
        ("Домашние задания", 30, "вручную"),
        ("Финал", 30, "вручную"),
        ("Проект", 20, "вручную"),
        ("Проходной балл", 65, None),
        ("Удержание %", 85, None),
        ("Посещаемость %", 75, None),
        ("Проходные %", 70, None),
    ]
    preview = (await admin.post(f"{S}/import", content=r.content)).json()
    assert preview["ok"] and preview["errors"] == [] and preview["sum"] == 100
    assert [(c["name"], c["weight"], c["kind"]) for c in preview["categories"]] == [
        (c["name"], c["weight"], c["kind"]) for c in WITH_PROJECT
    ]
    assert (preview["pass_score"], preview["target_attendance"]) == (65, 75)
    # applying what was understood changes nothing
    v = (await admin.get(S)).json()["version"]
    body = {
        k: preview[k]
        for k in ("pass_score", "target_retention", "target_attendance", "target_pass_rate")
    }
    r = await admin.patch(
        S,
        json={
            "categories": [
                {k: c[k] for k in ("name", "weight", "kind")} for c in preview["categories"]
            ],
            **body,
        },
    )
    assert r.status_code == 200 and r.json()["version"] == v
    assert "grading_scheme" in str(
        await sql("SELECT entity FROM audit_log WHERE action = 'export'")
    )


async def test_excel_import_reports_every_validation_error_in_russian(
    admin: httpx.AsyncClient,
) -> None:
    file = template_bytes(
        cats(("Посещаемость", 20, "attendance"), ("ДЗ", 30, "manual"), ("дз", 10, "manual")),
        [
            ["Проект", "много", "вручную"],
            ["Финал", 30, "иногда"],
            ["Проходной балл", 150, None],
            ["Очень " * 20, 10, "вручную"],
        ],
    )
    preview = (await admin.post(f"{S}/import", content=file)).json()
    assert preview["ok"] is False
    messages = [e["message"] for e in preview["errors"]]
    assert "Строка 4: категория «дз» уже есть в строке 3" in messages
    assert "Строка 5: баллы «много» — нужно целое число от 0 до 100" in messages
    assert "Строка 6: тип «иногда» — нужно «авто» или «вручную»" in messages
    assert "Строка 7: «Проходной балл» — нужно целое число от 0 до 100, а не «150»" in messages
    assert "Строка 8: название длиннее 60 символов" in messages
    assert "Сумма баллов 50 из 100: должно быть ровно 100" in messages
    no_att = (
        await admin.post(f"{S}/import", content=template_bytes(cats(("ДЗ", 100, "manual"))))
    ).json()
    assert [e["message"] for e in no_att["errors"]] == [
        "Категория «посещаемость» (авто) должна быть ровно одна, сейчас 0"
    ]
    # nothing was written
    assert (await admin.get(S)).json()["scheme"]["categories"] == DEFAULT


async def test_excel_import_hostile_files(admin: httpx.AsyncClient) -> None:
    url = f"{S}/import"
    # a zip bomb: tiny on the wire, huge inflated
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (60 * 1024 * 1024))
    r = await admin.post(url, content=bomb.getvalue())
    assert (r.status_code, r.json()["code"]) == (422, "import_unreadable")
    # too big
    r = await admin.post(url, content=b"x" * (2 * 1024 * 1024 + 1))
    assert (r.status_code, r.json()["code"]) == (413, "import_too_large")
    # NUL bytes, garbage, an empty file
    for junk in (b"\x00\x01\x02", b"PK\x03\x04garbage", b""):
        r = await admin.post(url, content=junk)
        assert r.status_code == 422, junk
    # too many rows
    r = await admin.post(
        url, content=template_bytes(DEFAULT, [[f"К{i}", 1, "вручную"] for i in range(80)])
    )
    assert (r.status_code, r.json()["code"]) == (422, "import_too_many_rows")
    # formulas are never calculated (no cached value = empty), control characters refused
    wb = Workbook()
    ws = wb.active
    ws.append(["Категория", "Баллы", "Тип"])
    ws.append(["Посещаемость", "=10+10", "авто"])
    ws.append(['=HYPERLINK("http://x","ДЗ")', 80, "вручную"])
    buf = io.BytesIO()
    wb.save(buf)
    preview = (await admin.post(url, content=buf.getvalue())).json()
    messages = [e["message"] for e in preview["errors"]]
    assert preview["ok"] is False
    assert "Строка 2: баллы «» — нужно целое число от 0 до 100" in messages
    assert "Строка 3: нет названия категории" in messages
    # control characters are refused (openpyxl cannot even write them: a CSV brings them)
    csv_bad = "Категория;Баллы;Тип\nПосещаемость;20;авто\nПлохо\x07;80;вручную\n".encode()
    preview = (await admin.post(url, content=csv_bad)).json()
    assert "Строка 3: недопустимые символы" in [e["message"] for e in preview["errors"]]
    # CSV with a formula-looking name from our own neutralised export comes back clean
    csv = "Категория;Баллы;Тип\nПосещаемость;20;авто\n'-Минус;80;вручную\n".encode()
    preview = (await admin.post(url, content=csv)).json()
    assert preview["ok"] and preview["categories"][1]["name"] == "-Минус"
