import httpx
import pytest

from app.audit.sentences import _count


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (1, "1 урок"),
        (2, "2 урока"),
        (5, "5 уроков"),
        (21, "21 урок"),
        (22, "22 урока"),
        (25, "25 уроков"),
        (11, "11 уроков"),
        (111, "111 уроков"),
    ],
)
def test_count_agrees_with_the_noun(n: int, text: str) -> None:
    assert _count(n, "урок", "урока", "уроков") == text


def test_marks_forms() -> None:
    assert [_count(n, "отметка", "отметки", "отметок") for n in (1, 2, 5)] == [
        "1 отметка",
        "2 отметки",
        "5 отметок",
    ]


async def test_malformed_id_in_the_path_is_not_found(admin: httpx.AsyncClient) -> None:
    for path in ("/api/v1/lessons/nope/attendance", "/api/v1/students/nope"):
        r = await admin.get(path)
        assert (r.status_code, r.json()["code"]) == (404, "not_found")
