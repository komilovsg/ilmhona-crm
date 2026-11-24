"""Certificates are issued, and reissued, only for a finished cohort («завершён»)."""

import httpx

from tests.certs import make_template
from tests.conftest import sql
from tests.money import enroll, running_cohort
from tests.test_certificate_registry import REG, graduates, issue, set_settings


async def active_graduate(admin: httpx.AsyncClient) -> tuple[dict, str]:
    """A running cohort whose student somebody set to «выпускник» by hand."""
    cohort = await running_cohort(admin, name="Run")
    eid = await enroll(admin, cohort, "Ручной Выпускник")
    await sql("UPDATE enrollment SET status = 'выпускник'")
    await sql("UPDATE student SET gender = 'male'")
    assert cohort["status"] != "завершён"
    return cohort, eid


async def test_certificate_batch_issue_needs_a_finished_cohort(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, eid = await active_graduate(admin)
    r = await issue(admin, cohort, tid, [eid])
    assert r.status_code == 409 and r.json()["code"] == "cohort_not_finished", r.text
    assert (await sql("SELECT count(*) FROM certificate"))[0][0] == 0
    assert (await sql("SELECT count(*) FROM enrollment WHERE certificate_no IS NOT NULL"))[0][
        0
    ] == 0


async def test_certificate_single_issue_needs_a_finished_cohort(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    _, eid = await active_graduate(admin)
    r = await admin.post(f"/api/v1/enrollments/{eid}/certificate", json={"template_id": tid})
    assert r.status_code == 409 and r.json()["code"] == "cohort_not_finished", r.text
    # the non-graduate switch does not lift it
    assert (await set_settings(admin, allow_non_graduate=True)).status_code == 200
    await sql("UPDATE enrollment SET status = 'активный'")
    r = await admin.post(
        f"/api/v1/enrollments/{eid}/certificate", json={"template_id": tid, "comment": "особый"}
    )
    assert r.status_code == 409 and r.json()["code"] == "cohort_not_finished", r.text


async def test_certificate_reissue_needs_a_finished_cohort(admin: httpx.AsyncClient) -> None:
    tid = await make_template()
    cohort, ids = await graduates(admin, 1)
    first = (await issue(admin, cohort, tid, list(ids.values()))).json()["items"][0]
    await sql("UPDATE cohort SET status = 'активный'")
    r = await admin.post(f"{REG}/{first['id']}/reissue", json={"comment": "опечатка"})
    assert r.status_code == 409 and r.json()["code"] == "cohort_not_finished", r.text
    assert (await sql("SELECT count(*) FROM certificate"))[0][0] == 1
    # the numbering other tests count from starts again
    await sql("ALTER SEQUENCE certificate_no_seq RESTART")
