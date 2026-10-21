"""Responses: JSON over ~1 KB is gzipped when the client accepts it, xlsx never is."""

import httpx

from tests.edu import make_student

STUDENTS = "/api/v1/students"
GZIP = {"Accept-Encoding": "gzip"}


async def test_large_json_is_gzipped_small_json_is_not(admin: httpx.AsyncClient) -> None:
    for i in range(30):
        await make_student(f"Студент {i:02d}")
    big = await admin.get(STUDENTS, headers=GZIP)
    assert big.headers["content-encoding"] == "gzip"
    assert len(big.json()["items"]) == 25  # the client still reads it as plain JSON
    plain = await admin.get(STUDENTS, headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    small = await admin.get("/api/health", headers=GZIP)
    assert "content-encoding" not in small.headers


async def test_api_responses_are_no_store(admin: httpx.AsyncClient) -> None:
    for i in range(30):
        await make_student(f"Студент {i:02d}")
    for url, headers in ((STUDENTS, GZIP), (f"{STUDENTS}/export", GZIP), ("/api/v1/auth/me", {})):
        r = await admin.get(url, headers=headers)
        assert r.headers["cache-control"] == "no-store", url
        assert r.headers["pragma"] == "no-cache", url
    assert (await admin.get(STUDENTS, headers=GZIP)).headers["content-encoding"] == "gzip"
    bad = await admin.get(f"{STUDENTS}/00000000-0000-0000-0000-000000000000")
    assert bad.status_code == 404 and bad.headers["cache-control"] == "no-store"
    assert (await admin.get("/api/health")).headers["cache-control"] == "no-cache"


async def test_xlsx_is_not_gzipped(admin: httpx.AsyncClient) -> None:
    for i in range(30):
        await make_student(f"Студент {i:02d}")
    r = await admin.get(f"{STUDENTS}/export", headers=GZIP)
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.content[:2] == b"PK"  # a zip, as xlsx is
