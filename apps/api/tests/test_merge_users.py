import httpx
import pytest

from app.cli import merge_command
from app.merge_users import KEPT_TABLES, MergeError
from tests.conftest import make_user, sql
from tests.edu import make_cohort, make_course, make_room


async def go(*args: str) -> tuple[int, str]:
    """Exit code and the text main() would print (it runs its own loop, so call the coroutine)."""
    try:
        return 0, await merge_command(args[1], args[3], "--dry-run" in args)
    except MergeError as e:
        return 1, str(e)


TABLES = ("cohort", "lesson", "instructor_payout", "audit_log", "app_user", "refresh_token")


async def counts() -> list[int]:
    return [(await sql(f"SELECT count(*) FROM {t}"))[0][0] for t in TABLES]


async def scene(admin: httpx.AsyncClient) -> tuple[str, str, str]:
    """Source `old` (instructor) with a cohort, its lessons, a payout, an audit row; target `main`."""
    main_id = await make_user("main", "superadmin")
    old_id = await make_user("old", "instructor")
    cohort = await make_cohort(
        admin, await make_course(), await make_room("Душанбе", "R1"), instructor_id=str(old_id)
    )
    await sql(
        "INSERT INTO instructor_payout (instructor_id, cohort_id, period, amount, paid_at, method) "
        "VALUES (:i, :c, '2026-01-01', 100, '2026-01-31', 'наличные')",
        i=old_id,
        c=cohort["id"],
    )
    await sql(
        "INSERT INTO audit_log (user_id, action, entity, entity_id) VALUES (:i, 'x.y', 'cohort', 'z')",
        i=old_id,
    )
    await sql(
        "INSERT INTO refresh_token (user_id, family_id, token_hash, expires_at) "
        "VALUES (:i, gen_random_uuid(), '\\x01', now() + interval '1 day')",
        i=old_id,
    )
    return str(main_id), str(old_id), cohort["id"]


async def test_dry_run_writes_nothing(admin: httpx.AsyncClient) -> None:
    await scene(admin)
    before = await counts()
    state = await sql("SELECT login, is_active, teaches, version FROM app_user ORDER BY login")
    code, out = await go("--from", "old", "--into", "main", "--dry-run")
    assert code == 0
    assert "cohort.instructor_id" in out and "moved" in out and "audit_log.user_id" in out
    assert "kept" in out and "dry run" in out
    assert await counts() == before
    assert (
        await sql("SELECT login, is_active, teaches, version FROM app_user ORDER BY login") == state
    )


async def test_real_run_moves_everything_but_history(admin: httpx.AsyncClient) -> None:
    main_id, old_id, cohort_id = await scene(admin)
    lessons = (await sql("SELECT count(*) FROM lesson WHERE instructor_id = :o", o=old_id))[0][0]
    assert lessons > 0
    code, out = await go("--from", "old", "--into", "main")
    assert code == 0
    assert "moved" in out
    q = "SELECT count(*) FROM {} WHERE instructor_id = :i"
    assert (await sql(q.format("cohort"), i=main_id))[0][0] == 1
    assert (await sql(q.format("cohort"), i=old_id))[0][0] == 0
    assert (await sql(q.format("lesson"), i=main_id))[0][0] == lessons
    assert (await sql(q.format("instructor_payout"), i=main_id))[0][0] == 1
    # history stays on the source
    assert (
        await sql("SELECT count(*) FROM audit_log WHERE user_id = :i AND action = 'x.y'", i=old_id)
    )[0][0] == 1
    assert (await sql("SELECT count(*) FROM audit_log WHERE action = 'user.merge'"))[0][0] == 1
    assert (
        await sql(
            "SELECT count(*) FROM refresh_token WHERE user_id = :i AND revoked_at IS NULL", i=old_id
        )
    )[0][0] == 0
    assert (await sql("SELECT is_active FROM app_user WHERE id = :i", i=old_id))[0][0] is False
    assert (await sql("SELECT teaches FROM app_user WHERE id = :i", i=main_id))[0][0] is True
    # the cohort version moved on through the trigger
    assert (await sql("SELECT version FROM cohort WHERE id = :c", c=cohort_id))[0][0] >= 2


async def test_unique_conflict_aborts_and_changes_nothing(admin: httpx.AsyncClient) -> None:
    main_id, old_id, _ = await scene(admin)
    await sql(
        "CREATE TABLE zz_cert (id serial PRIMARY KEY, user_id uuid REFERENCES app_user (id), "
        "kind text, UNIQUE (user_id, kind))"
    )
    try:
        for uid in (main_id, old_id):  # the same kind on both accounts
            await sql("INSERT INTO zz_cert (user_id, kind) VALUES (:u, 'A')", u=uid)
        await sql("INSERT INTO zz_cert (user_id, kind) VALUES (:u, 'B')", u=old_id)
        before = await counts()
        code, out = await go("--from", "old", "--into", "main")
        assert code == 1
        assert "zz_cert" in out and "CONFLICT" in out
        assert await counts() == before
        assert (await sql("SELECT count(*) FROM zz_cert WHERE user_id = :u", u=old_id))[0][0] == 2
        assert (await sql("SELECT is_active FROM app_user WHERE id = :i", i=old_id))[0][0] is True
        # a table nobody listed is found: without the conflict it moves
        await sql("DELETE FROM zz_cert WHERE user_id = :u", u=main_id)
        code, out = await go("--from", "old", "--into", "main")
        assert code == 0
        assert (await sql("SELECT count(*) FROM zz_cert WHERE user_id = :u", u=main_id))[0][0] == 2
    finally:
        await sql("DROP TABLE zz_cert")


async def test_both_accounts_in_one_row_are_counted(admin: httpx.AsyncClient) -> None:
    main_id, old_id, _ = await scene(admin)
    await sql(
        "CREATE TABLE zz_pair (id serial PRIMARY KEY, a uuid REFERENCES app_user (id), "
        "b uuid REFERENCES app_user (id))"
    )
    try:
        await sql("INSERT INTO zz_pair (a, b) VALUES (:m, :o)", m=main_id, o=old_id)
        code, out = await go("--from", "old", "--into", "main", "--dry-run")
        assert code == 0
        assert "rows with both accounts: zz_pair 1" in out
    finally:
        await sql("DROP TABLE zz_pair")


async def test_refusals(admin: httpx.AsyncClient) -> None:
    await scene(admin)
    await make_user("gone", "manager", active=False)
    before = await counts()
    for args in (
        ("--from", "old", "--into", "old"),
        ("--from", "nobody", "--into", "main"),
        ("--from", "old", "--into", "nobody"),
        ("--from", "old", "--into", "gone"),
    ):
        code, out = await go(*args)
        assert code == 1, args
    assert await counts() == before


async def test_refuses_the_last_active_superadmin() -> None:
    await make_user("boss", "superadmin")
    await make_user("inst", "instructor")
    code, out = await go("--from", "boss", "--into", "inst")
    assert code == 1
    assert "last active superadmin" in out
    assert (await sql("SELECT is_active FROM app_user WHERE login = 'boss'"))[0][0] is True


async def test_teaches_absent_dry_run_ok_real_run_refused(admin: httpx.AsyncClient) -> None:
    await scene(admin)
    await sql("ALTER TABLE app_user RENAME COLUMN teaches TO teaches_x")
    try:
        code, out = await go("--from", "old", "--into", "main", "--dry-run")
        assert code == 0
        assert "teaches column absent" in out
        code, out = await go("--from", "old", "--into", "main")
        assert code == 1
        assert "deploy migration 0020 first" in out
        assert (await sql("SELECT is_active FROM app_user WHERE login = 'old'"))[0][0] is True
    finally:
        await sql("ALTER TABLE app_user RENAME COLUMN teaches_x TO teaches")


def test_kept_tables_constant_and_error_type() -> None:
    assert "audit_log" in KEPT_TABLES and issubclass(MergeError, Exception)


def test_cli_requires_both_logins() -> None:
    from app.cli import main

    with pytest.raises(SystemExit):
        main(["merge-users", "--from", "a"])
