import re
from pathlib import Path

import app.main  # noqa: F401  (imports every package, so every code is registered)
from app.core.errors import errors

WEB_TEXTS = Path(__file__).parents[2] / "web" / "src" / "lib" / "api-errors.ts"


def _web_codes() -> set[str]:
    body = WEB_TEXTS.read_text().split("export const apiErrors", 1)[1].split("};", 1)[0]
    return set(re.findall(r"^\s{2}(\w+):", body, flags=re.M))


def test_every_error_code_has_a_russian_text_in_the_web_and_no_extras() -> None:
    api_codes = set(errors.codes())
    web = _web_codes()
    assert api_codes - web == set(), "add a text to apps/web/src/lib/api-errors.ts"
    assert web - api_codes == set(), "text for a code the API does not define"


def test_codes_are_snake_case() -> None:
    assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*", c) for c in errors.codes())


async def test_unknown_route_and_bad_body_use_the_registry(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/api/v1/nope")
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert r.headers["content-type"].startswith("application/problem+json")
    r = await client.post(
        "/api/v1/auth/login", content="not json", headers={"Content-Type": "application/json"}
    )
    assert r.json()["code"] == "validation_failed"
