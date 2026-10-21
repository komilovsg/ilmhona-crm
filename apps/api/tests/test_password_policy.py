import httpx

from app.core.password_policy import RULES, generate, violations
from tests.conftest import PASSWORD, make_user, sign_in


def test_each_rule_on_its_own() -> None:
    assert violations("Abcdefg1") == []
    assert violations("Ab1") == ["length"]
    assert violations("A" * 73 + "1") == ["length"]
    assert violations("12345678") == ["letter"]
    assert violations("abcdefgh") == ["digit"]
    assert violations("Anna12345", login="anna12345") == ["not_login"]
    assert violations("Abcdefg1", current="Abcdefg1") == ["not_current"]
    assert violations("абвгдеж1") == []  # any alphabet counts as a letter


def test_generated_passwords_pass_the_policy() -> None:
    for _ in range(50):
        assert violations(generate("anna")) == []


async def test_policy_endpoint_is_public_and_lists_the_rules(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/auth/password-policy")
    assert r.status_code == 200
    body = r.json()
    assert [x["id"] for x in body["rules"]] == [x["id"] for x in RULES]
    assert (body["min_length"], body["max_length"]) == (8, 72)


async def test_change_password_refuses_the_login(client: httpx.AsyncClient) -> None:
    await make_user("anna12345", "manager")
    await sign_in(client, "anna12345")
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "ANNA12345"},
    )
    assert r.json()["code"] == "weak_password"
