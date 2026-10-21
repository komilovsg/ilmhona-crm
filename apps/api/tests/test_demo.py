"""seed-demo makes a coherent fake dataset; wipe-demo removes exactly that and nothing else."""

import httpx

from app.cli import main, seed_command, wipe_command
from tests.conftest import make_user, sign_in, sql
from tests.edu import make_course, make_room, make_student

COUNTED = (
    "app_user",
    "room",
    "course",
    "cohort",
    "lesson",
    "student",
    "enrollment",
    "attendance",
    "grade",
    "payment",
    "instructor_payout",
    "lead",
    "campaign",
)


async def counts() -> dict[str, int]:
    return {t: (await sql(f"SELECT count(*) FROM {t}"))[0][0] for t in COUNTED}


async def test_seed_demo_covers_both_branches_and_every_table() -> None:
    before = await counts()
    assert await seed_command()
    after = await counts()
    for table in COUNTED:
        assert after[table] > before[table], table
    for table in ("cohort", "lead", "student", "room", "campaign"):
        names = await sql(
            f"SELECT DISTINCT b.name FROM {table} t JOIN branch b ON b.id = t.branch_id"
        )
        assert {r[0] for r in names} == {"Душанбе", "Истаравшан"}, table
    roles = await sql(
        "SELECT DISTINCT r.code FROM app_user u JOIN role r ON r.id = u.role_id "
        "WHERE u.login LIKE 'demo\\_%'"
    )
    assert {r[0] for r in roles} == {"superadmin", "manager", "instructor"}
    assert {r[0] for r in await sql("SELECT status FROM cohort")} == {
        "набор",
        "активный",
        "завершён",
    }


async def test_seed_demo_twice_is_refused() -> None:
    assert await seed_command()
    assert await seed_command() is None


async def test_wipe_demo_leaves_real_rows_alone() -> None:
    await make_user("real", "manager", branch="Душанбе")
    room = await make_room("Душанбе", "Настоящая")
    await make_course("Настоящий курс")
    await make_student("Настоящий Студент")
    before = await counts()
    assert await seed_command()
    assert await wipe_command() > 0
    assert await counts() == before
    assert (await sql("SELECT count(*) FROM room WHERE id = :i", i=room))[0][0] == 1
    # seed again after a wipe works
    assert await seed_command()


async def test_wipe_demo_is_marker_based_not_name_based() -> None:
    """A real user whose login merely looks like a demo one survives the wipe."""
    await make_user("demo_lookalike", "manager")
    assert await seed_command()
    await wipe_command()
    assert [r[0] for r in await sql("SELECT login FROM app_user")] == ["demo_lookalike"]


async def test_demo_user_can_sign_in(client: httpx.AsyncClient) -> None:
    password = await seed_command()
    assert password
    body = await sign_in(client, "demo_manager1", password)
    assert body["role"]["code"] == "manager"


def test_cli_knows_the_demo_commands() -> None:
    import pytest

    with pytest.raises(SystemExit):
        main(["seed-demo", "--nope"])
