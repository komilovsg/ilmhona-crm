import httpx

from app.cli import create_superadmin, main
from tests.conftest import sql


async def test_create_superadmin_prints_a_working_temp_password(client: httpx.AsyncClient) -> None:
    password = await create_superadmin("boss", "Босс")
    assert password
    r = await client.post("/api/v1/auth/login", json={"login": "boss", "password": password})
    assert r.status_code == 200
    body = r.json()
    assert body["role"]["code"] == "superadmin" and body["must_change_password"] is True
    (days,) = (
        await sql(
            "SELECT round(extract(epoch FROM temp_password_expires_at - now()) / 86400) FROM app_user"
        )
    )[0]
    assert days == 7


async def test_create_superadmin_refuses_an_existing_login() -> None:
    assert await create_superadmin("boss", "Босс")
    assert await create_superadmin("BOSS", "Босс") is None


def test_cli_argument_errors() -> None:
    import pytest

    with pytest.raises(SystemExit):
        main(["create-superadmin"])  # --login is required
