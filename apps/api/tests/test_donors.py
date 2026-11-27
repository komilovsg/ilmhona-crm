"""Free courses and donors: the donor list, cohort funding, who pays for a student, and the
money that follows from it (no debt, no payments for donor-funded students), the donor report,
the filters and the breakdown paying / donor / free."""

import uuid
from datetime import date
from io import BytesIO
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.audit.sentences import Entry, sentence
from app.core.db import sessionmaker
from app.permissions import MANAGER_DEFAULT
from tests.conftest import SignedIn, branch_id, make_role, sql
from tests.edu import C, body, make_course, make_room, make_student
from tests.money import P, cohort_money, enroll, money_of, pay, running_cohort, this_month
from tests.sales import L, make_lead

DON = "/api/v1/donors"
K = "/api/v1/dashboard/cards"


async def donor(c: httpx.AsyncClient, name: str = "Фонд Ага Хана", **kw: Any) -> str:
    r = await c.post(DON, json={"name": name, **kw})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def mixed(admin: httpx.AsyncClient, *donors: str, **kw: Any) -> dict[str, Any]:
    return await running_cohort(
        admin, funding="смешанный", donor_ids=list(donors), capacity=30, **kw
    )


async def enroll_by(
    c: httpx.AsyncClient, cohort: dict[str, Any], name: str, donor_id: str | None
) -> httpx.Response:
    sid = await make_student(name)
    body: dict[str, Any] = {"student_id": str(sid)}
    if donor_id is not None:
        body["donor_id"] = donor_id
    return await c.post(f"{C}/{cohort['id']}/enrollments", json=body)


async def enroll_donor(admin: httpx.AsyncClient, cohort: dict[str, Any], name: str, d: str) -> str:
    r = await enroll_by(admin, cohort, name, d)
    assert r.status_code == 201, r.text
    await sql(
        "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
        d=date.fromisoformat(cohort["start_date"]),
        i=r.json()["id"],
    )
    return str(r.json()["id"])


async def last_sentence(action: str) -> str:
    row = (
        await sql(
            "SELECT a.action, a.entity, a.label, a.diff, u.full_name FROM audit_log a "
            "LEFT JOIN app_user u ON u.id = a.user_id WHERE a.action = :a ORDER BY a.id DESC",
            a=action,
        )
    )[0]
    return sentence(Entry(row[4], row[0], row[1], row[2], row[3]))


# ---- the donor list ------------------------------------------------------------------------


async def test_donor_crud_archive_and_audit(admin: httpx.AsyncClient) -> None:
    d = await donor(admin, note="грант на 2026")
    assert (await admin.post(DON, json={"name": "Фонд Ага Хана"})).status_code == 409
    r = await admin.patch(f"{DON}/{d}", json={"note": "грант продлён"})
    assert r.status_code == 200 and r.json()["note"] == "грант продлён"
    r = await admin.patch(f"{DON}/{d}", json={"archived": True})
    assert r.json()["archived"] is True
    assert "перенесён в архив донор Фонд Ага Хана" in await last_sentence("donor.archive")
    assert "добавлен донор Фонд Ага Хана" in await last_sentence("donor.create")
    assert "заметка" in await last_sentence("donor.update")
    # stale version: 409
    r = await admin.patch(f"{DON}/{d}", json={"name": "X"}, headers={"X-Record-Version": "1"})
    assert r.status_code == 409
    assert [x["archived"] for x in (await admin.get(DON)).json()] == [True]
    assert (await admin.get(DON, params={"archived": False})).json() == []
    # an archived donor is not offered for a new cohort
    r = await admin.post(
        C,
        json={**(await _cohort_body(admin)), "funding": "донор", "donor_ids": [d]},
    )
    assert r.status_code == 422 and r.json()["code"] == "donor_archived"
    r = await admin.get(f"{DON}/export")
    assert r.status_code == 200
    ws = load_workbook(BytesIO(r.content)).active
    assert ws is not None and ws["A2"].value == "Фонд Ага Хана"


async def _cohort_body(admin: httpx.AsyncClient) -> dict[str, Any]:
    return body(
        await make_course("Курс Z", 500),
        await make_room("Душанбе", "R-Z"),
        branch_id=str(await branch_id("Душанбе")),
    )


async def test_donor_rights(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    d = await donor(admin)
    no_donors = {k: v for k, v in MANAGER_DEFAULT.items() if k != "donors"}
    plain = await login_as("mgr", await make_role("М", no_donors), branch="Душанбе")
    # no `donors` right: no directory, no report, no writes; the picker follows `cohorts`
    assert (await plain.get(DON)).status_code == 403
    assert (await plain.get(f"{DON}/report")).status_code == 403
    assert (await plain.post(DON, json={"name": "Новый"})).status_code == 403
    assert (await plain.patch(f"{DON}/{d}", json={"note": "x"})).status_code == 403
    assert [o["id"] for o in (await plain.get(f"{DON}/options")).json()] == [d]
    viewer = await login_as(
        "view", await make_role("Д", {**MANAGER_DEFAULT, "donors": "view"}), branch="Душанбе"
    )
    assert (await viewer.get(DON)).status_code == 200
    assert (await viewer.post(DON, json={"name": "Новый"})).status_code == 403
    editor = await login_as("edit", await make_role("Е", {"donors": "change"}))
    assert (await editor.post(DON, json={"name": "Новый"})).status_code == 201
    teacher = await login_as("ins", "instructor")
    assert (await teacher.post(DON, json={"name": "Ещё"})).status_code == 403
    assert (await teacher.get(DON)).status_code == 403
    assert (await teacher.get(f"{DON}/report")).status_code == 403
    # cohorts view: the picker only, and only the donors of their own cohorts (none yet)
    r = await teacher.get(f"{DON}/options")
    assert r.status_code == 200 and r.json() == []


async def test_seeded_manager_role_views_donors_and_report(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    d = await donor(admin, "Фонд М")
    cohort = await running_cohort(admin, funding="донор", donor_ids=[d], capacity=30)
    await enroll_donor(admin, cohort, "Студент М", d)
    rights = await sql(
        "SELECT rp.level FROM role_permission rp JOIN role r ON r.id = rp.role_id "
        "WHERE r.code = 'manager' AND rp.section = 'donors'"
    )
    assert rights == [("view",)]
    mgr = await login_as("mgr", "manager", branch="Душанбе")
    r = await mgr.get(DON)
    assert r.status_code == 200 and [x["name"] for x in r.json()] == ["Фонд М"]
    r = await mgr.get(f"{DON}/report")
    assert r.status_code == 200, r.text
    assert [(x["donor_name"], x["enrolled"]) for x in r.json()["items"]] == [("Фонд М", 1)]
    assert (await mgr.get(f"{DON}/report/export")).status_code == 200
    assert (await mgr.post(DON, json={"name": "Нельзя"})).status_code == 403


NEW_STUDENT = {"new_student": {"full_name": "Новый Студент", "phone": None, "gender": None}}


async def test_instructor_enrolls_with_a_donor_of_own_cohort_only(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    """The instructor's add-student form: the donor picker of a donor cohort with several donors.
    Own cohort only; the donor must fund that cohort; the picker lists no other cohort's donor."""
    d1, d2, d3 = await donor(admin, "Д1"), await donor(admin, "Д2"), await donor(admin, "Д3")
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    own = await running_cohort(
        admin, name="O", funding="донор", donor_ids=[d1, d2], capacity=30, instructor_id=me
    )
    other = await running_cohort(admin, name="X", funding="донор", donor_ids=[d1, d3], capacity=30)
    # the picker: the donors of the instructor's cohorts only, never the whole list
    r = await ins.get(f"{DON}/options")
    assert r.status_code == 200 and sorted(o["name"] for o in r.json()) == ["Д1", "Д2"]
    r = await ins.get(f"{C}/{own['id']}")
    assert r.status_code == 200 and sorted(x["name"] for x in r.json()["donors"]) == ["Д1", "Д2"]
    assert (await ins.get(f"{C}/{other['id']}")).status_code == 404
    # several donors: one must be chosen
    url = f"{C}/{own['id']}/enrollments"
    r = await ins.post(url, json=NEW_STUDENT)
    assert (r.status_code, r.json()["code"]) == (422, "donor_required")
    # a donor that does not fund this cohort (it funds another one) is refused
    r = await ins.post(url, json={**NEW_STUDENT, "donor_id": d3})
    assert (r.status_code, r.json()["code"]) == (422, "donor_not_in_cohort")
    r = await ins.post(url, json={**NEW_STUDENT, "donor_id": d2})
    assert r.status_code == 201 and r.json()["donor_id"] == d2
    # another instructor's cohort: not found, nothing written
    r = await ins.post(f"{C}/{other['id']}/enrollments", json={**NEW_STUDENT, "donor_id": d1})
    assert r.status_code == 404
    assert await sql("SELECT count(*) FROM enrollment WHERE cohort_id = :c", c=other["id"]) == [
        (0,)
    ]
    # an existing student stays a manager's choice, donor or not
    sid = await make_student("Старый")
    r = await ins.post(url, json={"student_id": str(sid), "donor_id": d1})
    assert r.status_code == 403


# ---- cohort funding ------------------------------------------------------------------------


async def test_funding_rules_of_a_cohort(admin: httpx.AsyncClient) -> None:
    d1, d2 = await donor(admin, "Д1"), await donor(admin, "Д2")
    base = await _cohort_body(admin)
    # «донор» needs a donor, «платный» / «бесплатный» take none
    for funding, donors in (("донор", []), ("платный", [d1]), ("бесплатный", [d1])):
        r = await admin.post(C, json={**base, "funding": funding, "donor_ids": donors})
        assert r.status_code == 422, (funding, r.text)
        assert r.json()["code"] == "funding_donors_invalid"
    r = await admin.post(C, json={**base, "funding": "бесплатный", "price_month": "300"})
    assert r.status_code == 201 and r.json()["price_month"] == "0.00"
    free = r.json()
    r = await admin.patch(f"{C}/{free['id']}", json={"price_month": "100"})
    assert r.status_code == 422
    r = await admin.post(
        C, json={**base, "start_time": "12:00", "end_time": "13:00", "funding": "донор",
                 "donor_ids": [d1, d2]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    cohort = r.json()
    assert cohort["funding"] == "донор"
    assert sorted(x["name"] for x in cohort["donors"]) == ["Д1", "Д2"]
    # several donors: the student's donor must be chosen; a donor of no cohort is refused
    r = await enroll_by(admin, cohort, "Без донора", None)
    assert r.status_code == 422 and r.json()["code"] == "donor_required"
    d3 = await donor(admin, "Д3")
    r = await enroll_by(admin, cohort, "Чужой донор", d3)
    assert r.status_code == 422 and r.json()["code"] == "donor_not_in_cohort"
    r = await enroll_by(admin, cohort, "С донором", d2)
    assert r.status_code == 201 and r.json()["donor_id"] == d2
    assert "за счёт донора Д2" in await last_sentence("enrollment.create")
    # a donor with students cannot leave the cohort
    r = await admin.patch(f"{C}/{cohort['id']}", json={"donor_ids": [d1]})
    assert r.status_code == 409 and r.json()["code"] == "donor_in_use"
    r = await admin.patch(f"{C}/{cohort['id']}", json={"donor_ids": [d2]})
    assert r.status_code == 200 and [x["name"] for x in r.json()["donors"]] == ["Д2"]
    # a paid cohort takes no donor for a student
    paid = await running_cohort(admin, name="P")
    r = await enroll_by(admin, paid, "Платник", d1)
    assert r.status_code == 422 and r.json()["code"] == "donor_not_in_cohort"


async def test_one_donor_is_set_by_itself_and_mixed_to_donor_moves_payers(
    admin: httpx.AsyncClient,
) -> None:
    d = await donor(admin, "Один")
    cohort = await running_cohort(admin, funding="донор", donor_ids=[d], capacity=30)
    r = await enroll_by(admin, cohort, "Авто", None)
    assert r.status_code == 201 and r.json()["donor_id"] == d
    other = await mixed(admin, d, name="M")
    payer = await enroll(admin, other, "Платник")
    r = await admin.patch(f"{C}/{other['id']}", json={"funding": "донор"})
    assert r.status_code == 200, r.text
    rows = await sql("SELECT donor_id FROM enrollment WHERE id = :i", i=payer)
    assert str(rows[0][0]) == d
    # back to «платный»: refused while the donor has students
    r = await admin.patch(f"{C}/{other['id']}", json={"funding": "платный"})
    assert r.status_code == 409 and r.json()["code"] == "donor_in_use"


# ---- money -------------------------------------------------------------------------------


async def test_mixed_cohort_10_payers_10_donor_expected_5000(admin: httpx.AsyncClient) -> None:
    """TZ check: price 500, 10 payers + 10 donor students → this month expects 5000, only the
    payers are debtors, the donor report shows 10 students."""
    d = await donor(admin, "Фонд")
    cohort = await mixed(admin, d, back=0)
    payers = [await enroll(admin, cohort, f"Платник {i:02}") for i in range(10)]
    funded = [await enroll_donor(admin, cohort, f"Донорский {i:02}", d) for i in range(10)]
    r = await admin.get(f"{K}/month")
    assert r.status_code == 200, r.text
    hero = r.json()
    assert float(hero["expected"]) == 5000.0
    assert hero["debtors"] == 10 and float(hero["debt"]) == 5000.0
    r = await admin.get(f"{P}/debtors", params={"page_size": 100})
    debtors = {x["enrollment_id"] for x in r.json()["items"]}
    assert debtors == set(payers) and float(r.json()["total_debt"]) == 5000.0
    money = await cohort_money(admin, cohort)
    assert money["seats"] == {"paying": 10, "donor": 10, "free": 0}
    assert all(money_of(money, e)["debt"] == "0.00" for e in funded)
    report = (await admin.get(f"{DON}/report", params={"donor_id": d})).json()
    assert report["donors"][0]["enrolled"] == 10 and report["items"][0]["studying"] == 10
    overview = (await admin.get("/api/v1/dashboard/overview")).json()
    assert overview["funding"] == {"paying": 10, "donor": 10, "free": 0}
    assert float(overview["debt"]) == 5000.0


async def test_no_payment_for_a_donor_student(admin: httpx.AsyncClient) -> None:
    d = await donor(admin)
    cohort = await mixed(admin, d)
    funded = await enroll_donor(admin, cohort, "Донорский", d)
    payer = await enroll(admin, cohort, "Платник")
    r = await admin.post(
        P,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "enrollment_id": funded,
            "month_no": 1,
            "amount": "500",
            "method": "alif",
            "paid_at": this_month().isoformat(),
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "payment_donor_funded"
    options = (await admin.get(f"{P}/options", params={"cohort_id": cohort["id"]})).json()
    assert [o["enrollment_id"] for o in options] == [payer]
    # a discount (task 6) is for payers only: the payer still gets one
    await pay(admin, payer, amount="400", discount_percent=20, note="скидка")


async def test_from_donor_to_paying_counts_debt_from_that_month(
    admin: httpx.AsyncClient,
) -> None:
    d = await donor(admin)
    cohort = await mixed(admin, d, back=2)  # month 3 of the cohort is this month
    e = await enroll_donor(admin, cohort, "Переведённый", d)
    assert money_of(await cohort_money(admin, cohort), e)["debt"] == "0.00"
    r = await admin.patch(f"/api/v1/enrollments/{e}/funding", json={"donor_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["donor_id"] is None and r.json()["pays_from"] is not None
    m = money_of(await cohort_money(admin, cohort), e)
    assert (m["expected"], m["debt"]) == ("500.00", "500.00")  # this month only, not 1500
    assert [x["month_no"] for x in m["due_months"]] == [3]
    assert "Донор: Фонд Ага Хана → Платит сам" in await last_sentence("enrollment.funding")
    # and back to the donor: owes nothing again
    r = await admin.patch(f"/api/v1/enrollments/{e}/funding", json={"donor_id": d})
    assert r.status_code == 200
    assert money_of(await cohort_money(admin, cohort), e)["debt"] == "0.00"
    # a «донор» cohort has no «платит сам»
    only = await running_cohort(admin, name="D", funding="донор", donor_ids=[d])
    e2 = await enroll_donor(admin, only, "Только донор", d)
    r = await admin.patch(f"/api/v1/enrollments/{e2}/funding", json={"donor_id": None})
    assert r.status_code == 422 and r.json()["code"] == "donor_required"


async def test_free_cohort_owes_nothing_and_counts_as_free(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, funding="бесплатный")
    e = await enroll(admin, cohort, "Бесплатник")
    m = await cohort_money(admin, cohort)
    assert m["seats"] == {"paying": 0, "donor": 0, "free": 1}
    assert money_of(m, e)["debt"] == "0.00"
    r = await admin.get(f"{P}/debtors")
    assert r.json()["total"] == 0


async def test_master_list_ltv_counts_paying_seats_only(admin: httpx.AsyncClient) -> None:
    d = await donor(admin)
    cohort = await mixed(admin, d)
    payer = await enroll(admin, cohort, "Платник")
    await enroll_donor(admin, cohort, "Донорский 1", d)
    await enroll_donor(admin, cohort, "Донорский 2", d)
    await pay(admin, payer, confirm=True)
    r = await admin.get("/api/v1/master-list")
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["items"] if x["cohort_id"] == cohort["id"])
    assert (row["enrolled"], row["paying"], row["by_donor"], row["free"]) == (3, 1, 2, 0)
    assert float(row["ltv"]) == 500.0  # 500 ÷ 1 payer, not ÷ 3


# ---- report, filters, scope ----------------------------------------------------------------


async def test_donor_report_counts_and_excel(admin: httpx.AsyncClient) -> None:
    d = await donor(admin, "Фонд")
    cohort = await mixed(admin, d)
    ids = [await enroll_donor(admin, cohort, f"С{i}", d) for i in range(5)]
    await sql("UPDATE enrollment SET status = 'отчислен' WHERE id = :i", i=ids[0])
    await sql("UPDATE enrollment SET status = 'выпускник' WHERE id IN (:a, :b)", a=ids[1], b=ids[2])
    sid = (await sql("SELECT student_id FROM enrollment WHERE id = :i", i=ids[1]))[0][0]
    await sql(
        "INSERT INTO employment (student_id, organization, employed_at) "
        "VALUES (:s, 'ООО Тест', '2026-10-01')",
        s=sid,
    )
    await enroll(admin, cohort, "Платник")  # not the donor's
    r = await admin.get(f"{DON}/report")
    item = r.json()["items"][0]
    assert {k: item[k] for k in ("enrolled", "studying", "expelled", "graduated", "employed")} == {
        "enrolled": 5,
        "studying": 2,
        "expelled": 1,
        "graduated": 2,
        "employed": 1,
    }
    r = await admin.get(f"{DON}/report/export", params={"donor_id": d})
    assert r.status_code == 200
    ws = load_workbook(BytesIO(r.content)).active
    assert ws is not None
    header = [c.value for c in ws[1]]
    assert header[:2] == ["Донор", "Поток"] and ws["A2"].value == "Фонд"
    assert ws.cell(2, header.index("Зачислено") + 1).value == 5


async def test_donor_report_and_filters_follow_branch_scope(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    d = await donor(admin)
    here = await mixed(admin, d, name="Д")
    there = await mixed(admin, d, name="Х", branch="Истаравшан")
    await enroll_donor(admin, here, "Здесь", d)
    sid = await make_student("Там", "Истаравшан")
    r = await admin.post(
        f"{C}/{there['id']}/enrollments", json={"student_id": str(sid), "donor_id": d}
    )
    assert r.status_code == 201, r.text
    assert len((await admin.get(f"{DON}/report")).json()["items"]) == 2
    mgr = await login_as(
        "mgr", await make_role("Д", {**MANAGER_DEFAULT, "donors": "view"}), branch="Душанбе"
    )
    items = (await mgr.get(f"{DON}/report")).json()["items"]
    assert [i["cohort_id"] for i in items] == [here["id"]]
    cohorts = (await mgr.get(C, params={"donor_id": d})).json()["items"]
    assert [c["id"] for c in cohorts] == [here["id"]]
    students = (await mgr.get("/api/v1/students", params={"donor_id": d})).json()["items"]
    assert [s["full_name"] for s in students] == ["Здесь"]
    # the admin's filters: cohorts and students of the donor only
    plain = await running_cohort(admin, name="П")
    await enroll(admin, plain, "Платник")
    assert {c["id"] for c in (await admin.get(C, params={"donor_id": d})).json()["items"]} == {
        here["id"],
        there["id"],
    }
    r = await admin.get("/api/v1/students", params={"donor_id": d})
    names = {s["full_name"] for s in r.json()["items"]}
    assert names == {"Здесь", "Там"}


async def test_graduates_filter_by_donor(admin: httpx.AsyncClient) -> None:
    d = await donor(admin)
    cohort = await mixed(admin, d)
    a = await enroll_donor(admin, cohort, "Донорский выпускник", d)
    b = await enroll(admin, cohort, "Платный выпускник")
    await sql("UPDATE enrollment SET status = 'выпускник' WHERE id IN (:a, :b)", a=a, b=b)
    r = await admin.get("/api/v1/graduates/students", params={"donor_id": d})
    assert r.status_code == 200, r.text
    assert [x["student_name"] for x in r.json()["items"]] == ["Донорский выпускник"]


async def test_lead_convert_into_a_donor_cohort(admin: httpx.AsyncClient) -> None:
    d1, d2 = await donor(admin, "Д1"), await donor(admin, "Д2")
    cohort = await running_cohort(admin, funding="донор", donor_ids=[d1, d2])
    lead = await make_lead(admin, "Лид Донорский")
    r = await admin.post(f"{L}/{lead['id']}/convert", json={"cohort_id": cohort["id"]})
    assert r.status_code == 422 and r.json()["code"] == "donor_required"
    r = await admin.post(
        f"{L}/{lead['id']}/convert", json={"cohort_id": cohort["id"], "donor_id": d2}
    )
    assert r.status_code == 200, r.text
    rows = await sql(
        "SELECT donor_id FROM enrollment WHERE id = :i", i=r.json()["enrollment"]["id"]
    )
    assert str(rows[0][0]) == d2


async def test_cohort_list_shows_funding_and_seats(admin: httpx.AsyncClient) -> None:
    d = await donor(admin, "Фонд")
    cohort = await mixed(admin, d)
    await enroll(admin, cohort, "Платник")
    await enroll_donor(admin, cohort, "Донорский", d)
    item = next(c for c in (await admin.get(C)).json()["items"] if c["id"] == cohort["id"])
    assert item["funding"] == "смешанный" and item["seats"] == {"paying": 1, "donor": 1, "free": 0}
    r = await admin.get(f"{C}/{cohort['id']}/enrollments/export")
    ws = load_workbook(BytesIO(r.content)).active
    assert ws is not None
    labels = {ws.cell(i, 4).value for i in range(2, 4)}
    assert labels == {"Платит сам", "Донор: Фонд"}


async def test_existing_cohorts_with_price_0_read_as_free() -> None:
    """Migration 0031: «бесплатный» needs a price of 0 (the old price-0 cohorts became free)."""
    room, course = await make_room("Душанбе", "R-F"), await make_course("F", 0)
    async with sessionmaker() as db:
        with pytest.raises(IntegrityError):
            await db.execute(
                text(
                    "INSERT INTO cohort (course_id, branch_id, room_id, start_date, end_date,"
                    " weekdays, start_time, end_time, capacity, price_month, funding) "
                    "SELECT :c, branch_id, id, '2026-01-05', '2026-03-05', '{1}', '10:00',"
                    " '11:00', 10, 100, 'бесплатный' FROM room WHERE id = :r"
                ),
                {"c": course, "r": room},
            )


async def test_mixed_cohort_without_donors(admin: httpx.AsyncClient) -> None:
    cohort = await mixed(admin, back=0)
    assert cohort["funding"] == "смешанный" and cohort["donors"] == []
    r = await enroll_by(admin, cohort, "Сам платит", None)
    assert r.status_code == 201, r.text
    assert r.json()["donor_id"] is None
    eid = r.json()["id"]
    assert float((await cohort_money(admin, cohort))["seats"]["paying"]) == 1
    assert money_of(await cohort_money(admin, cohort), eid)["debt"] != "0.00"
    # a donor added later can be picked
    d = await donor(admin, "Позже")
    r = await admin.patch(f"{C}/{cohort['id']}", json={"donor_ids": [d]})
    assert r.status_code == 200, r.text
    r = await enroll_by(admin, cohort, "С донором", d)
    assert r.status_code == 201 and r.json()["donor_id"] == d
    # back to no donors is refused while one is used; edit to none works on an unused cohort
    other = await mixed(admin, d, name="M2")
    r = await admin.patch(f"{C}/{other['id']}", json={"donor_ids": []})
    assert r.status_code == 200, r.text


# ---- «не платит» -------------------------------------------------------------------------


async def _mark(c: httpx.AsyncClient, e: str, **body: Any) -> httpx.Response:
    return await c.patch(f"/api/v1/enrollments/{e}/funding", json={"donor_id": None, **body})


async def test_not_paying_student_owes_nothing_and_pays_nothing(
    admin: httpx.AsyncClient,
) -> None:
    for funding in ("платный", "смешанный"):
        cohort = await running_cohort(admin, name=funding, funding=funding, back=1, capacity=30)
        e = await enroll(admin, cohort, f"Бесплатник {funding}")
        payer = await enroll(admin, cohort, f"Платник {funding}")
        r = await _mark(admin, e, not_paying=True)
        assert r.status_code == 200, r.text
        assert r.json()["not_paying"] is True and r.json()["donor_id"] is None
        assert "учится бесплатно" in await last_sentence("enrollment.funding")
        money = await cohort_money(admin, cohort)
        assert money_of(money, e)["debt"] == "0.00" and money_of(money, e)["expected"] == "0.00"
        assert money_of(money, payer)["debt"] != "0.00"
        # a free seat, not a donor's one
        assert money["seats"] == {"paying": 1, "donor": 0, "free": 1}
        r = await admin.post(
            P,
            json={
                "idempotency_key": str(uuid.uuid4()),
                "enrollment_id": e,
                "month_no": 1,
                "amount": "500",
                "method": "alif",
                "paid_at": this_month().isoformat(),
            },
        )
        assert r.status_code == 409 and r.json()["code"] == "payment_not_paying"
        options = (await admin.get(f"{P}/options", params={"cohort_id": cohort["id"]})).json()
        assert [o["enrollment_id"] for o in options] == [payer]
        r = await admin.get(f"{P}/debtors", params={"page_size": 100})
        assert e not in {x["enrollment_id"] for x in r.json()["items"]}


async def test_not_paying_enroll_and_refusals(admin: httpx.AsyncClient) -> None:
    d = await donor(admin, "Фонд")
    paid = await running_cohort(admin, name="P", capacity=30)
    sid = await make_student("Сразу бесплатно")
    r = await admin.post(
        f"{C}/{paid['id']}/enrollments", json={"student_id": str(sid), "not_paying": True}
    )
    assert r.status_code == 201 and r.json()["not_paying"] is True, r.text
    assert "(не платит)" in await last_sentence("enrollment.create")
    # never with a donor
    cohort = await mixed(admin, d, name="M")
    sid = await make_student("Донор и бесплатно")
    r = await admin.post(
        f"{C}/{cohort['id']}/enrollments",
        json={"student_id": str(sid), "donor_id": d, "not_paying": True},
    )
    assert r.status_code == 422 and r.json()["code"] == "not_paying_with_donor"
    funded = await enroll_donor(admin, cohort, "Донорский", d)
    r = await admin.patch(
        f"/api/v1/enrollments/{funded}/funding", json={"donor_id": d, "not_paying": True}
    )
    assert r.status_code == 422 and r.json()["code"] == "not_paying_with_donor"
    async with sessionmaker() as db:
        with pytest.raises(IntegrityError):
            await db.execute(
                text("UPDATE enrollment SET not_paying = true WHERE id = :i"), {"i": funded}
            )
    # meaningless where nobody pays: «бесплатный» and «донор» cohorts refuse it
    free = await running_cohort(admin, name="F", funding="бесплатный")
    e = await enroll(admin, free, "В бесплатном")
    r = await _mark(admin, e, not_paying=True)
    assert r.status_code == 422 and r.json()["code"] == "not_paying_funding"
    only = await running_cohort(admin, name="D", funding="донор", donor_ids=[d])
    e = await enroll_donor(admin, only, "В донорском", d)
    r = await _mark(admin, e, not_paying=True)
    assert r.status_code == 422 and r.json()["code"] == "not_paying_funding"
    sid = await make_student("Новый в донорском")
    r = await admin.post(
        f"{C}/{only['id']}/enrollments", json={"student_id": str(sid), "not_paying": True}
    )
    assert r.status_code == 422 and r.json()["code"] == "not_paying_funding"


async def test_from_not_paying_to_paying_counts_debt_from_that_month(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin, back=2, capacity=30)  # month 3 is this month
    e = await enroll(admin, cohort, "Снова платит")
    assert (await _mark(admin, e, not_paying=True)).status_code == 200
    assert money_of(await cohort_money(admin, cohort), e)["debt"] == "0.00"
    r = await _mark(admin, e)
    assert r.status_code == 200, r.text
    assert r.json()["not_paying"] is False and r.json()["pays_from"] is not None
    m = money_of(await cohort_money(admin, cohort), e)
    assert (m["expected"], m["debt"]) == ("500.00", "500.00")  # this month only, not 1500
    assert [x["month_no"] for x in m["due_months"]] == [3]
    assert "снова платит с " in await last_sentence("enrollment.funding")


async def test_cohort_to_donor_clears_not_paying(admin: httpx.AsyncClient) -> None:
    d = await donor(admin, "Один")
    cohort = await mixed(admin, d, name="M")
    e = await enroll(admin, cohort, "Был бесплатным")
    assert (await _mark(admin, e, not_paying=True)).status_code == 200
    r = await admin.patch(f"{C}/{cohort['id']}", json={"funding": "донор"})
    assert r.status_code == 200, r.text
    rows = await sql("SELECT donor_id, not_paying FROM enrollment WHERE id = :i", i=e)
    assert (str(rows[0][0]), rows[0][1]) == (d, False)


async def test_migration_0037_round_trip() -> None:
    """Up adds `enrollment.not_paying` with its donor check, down drops it, up again works."""
    import asyncio

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.conftest import SERVER_URL, TEST_DB

    name = f"{TEST_DB}_mig_np"
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await server.dispose()
    url = SERVER_URL.set(database=name)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    engine = create_async_engine(url)
    q = text(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = 'enrollment' AND column_name = 'not_paying'"
    )
    try:
        seen = []
        for step, rev in ((command.upgrade, "0037"), (command.downgrade, "0036")):
            await asyncio.to_thread(step, cfg, rev)
            async with engine.connect() as conn:
                seen.append((await conn.execute(q)).scalar_one())
        await asyncio.to_thread(command.upgrade, cfg, "0037")
        async with engine.connect() as conn:
            seen.append((await conn.execute(q)).scalar_one())
        assert seen == [1, 0, 1]
    finally:
        await engine.dispose()
