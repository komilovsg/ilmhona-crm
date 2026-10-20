"""CSV of leads (a Facebook lead-form export or any table with a header row): parsing, column
mapping and row normalisation. Pure: nothing here touches the database, so a preview can never
write anything. The limits keep a hostile or mistaken file from eating the server."""

import csv
import io
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import DomainError
from app.leads.errors import (
    IMPORT_MAPPING_INVALID,
    IMPORT_NO_ROWS,
    IMPORT_TOO_LARGE,
    IMPORT_TOO_MANY_ROWS,
    IMPORT_UNREADABLE,
)
from app.leads.hygiene import clean_name, neutral, phone_parts

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
MAX_CELL = 2000
FIELDS = ("full_name", "first_name", "last_name", "phone", "source", "course", "comment")
SOURCES = (
    "Facebook",
    "Instagram",
    "TikTok",
    "Telegram",
    "сайт",
    "рекомендация",
    "звонок",
    "другое",
)
_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": (
        "full_name",
        "fullname",
        "name",
        "fio",
        "фио",
        "имя",
        "полное имя",
        "имя и фамилия",
    ),
    "first_name": ("first_name", "firstname", "имя"),
    "last_name": ("last_name", "lastname", "surname", "фамилия"),
    "phone": ("phone_number", "phone", "телефон", "номер телефона", "mobile", "tel", "номер"),
    "source": ("platform", "source", "источник"),
    "course": ("course", "курс", "направление"),
    "comment": ("comment", "комментарий", "message", "сообщение"),
}
_SOURCE_WORDS = (
    ("Facebook", ("facebook", "fb")),
    ("Instagram", ("instagram", "ig", "insta")),
    ("TikTok", ("tiktok", "tik tok")),
    ("Telegram", ("telegram", "tg", "телеграм")),
    ("сайт", ("сайт", "site", "web", "website")),
    ("рекомендация", ("рекомендац", "referral")),
    ("звонок", ("звонок", "call")),
)


def decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1251")
        except UnicodeDecodeError:
            raise DomainError(IMPORT_UNREADABLE) from None


def parse_csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    """(header, rows). The delimiter is the most frequent of , ; tab in the first line."""
    if len(data) > MAX_BYTES:
        raise DomainError(IMPORT_TOO_LARGE, limit=MAX_BYTES)
    text = decode(data)
    if "\x00" in text:
        raise DomainError(IMPORT_UNREADABLE)
    first = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=first.count)
    try:
        table = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(r)]
    except csv.Error:
        raise DomainError(IMPORT_UNREADABLE) from None
    if len(table) < 2:
        raise DomainError(IMPORT_NO_ROWS)
    header = [h.strip() for h in table[0]]
    rows = table[1:]
    if len(rows) > MAX_ROWS:
        raise DomainError(IMPORT_TOO_MANY_ROWS, limit=MAX_ROWS)
    return header, rows


def detect_mapping(header: list[str]) -> dict[str, str | None]:
    """field -> the header of the column that holds it (None: not found). The first match wins
    and a column is used for one field only («Имя» alone is the full name, not the first name)."""
    lowered = {h.strip().lower(): h for h in header}
    mapping: dict[str, str | None] = dict.fromkeys(FIELDS)
    taken: set[str] = set()
    for fld in FIELDS:
        for alias in _ALIASES[fld]:
            col = lowered.get(alias)
            if col is not None and col not in taken:
                mapping[fld] = col
                taken.add(col)
                break
    return mapping


def complete(mapping: dict[str, str | None]) -> bool:
    return bool(mapping["full_name"] or mapping["first_name"] or mapping["last_name"]) or bool(
        mapping["phone"]
    )


def check_mapping(
    header: list[str], mapping: dict[str, str | None], *, strict: bool = True
) -> dict[str, str | None]:
    """A column that does not exist is always an error; a mapping with neither a name nor a
    phone is one only when `strict` (the preview shows the columns so the user can pick)."""
    clean: dict[str, str | None] = dict.fromkeys(FIELDS)
    for fld in FIELDS:
        col = mapping.get(fld)
        if col is not None and col not in header:
            raise DomainError(IMPORT_MAPPING_INVALID)
        clean[fld] = col or None
    if strict and not complete(clean):
        raise DomainError(IMPORT_MAPPING_INVALID)
    return clean


def source_of(value: str | None, default: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return default
    for source, words in _SOURCE_WORDS:
        if any(text == w or text.startswith(w) for w in words):
            return source
    return default


@dataclass
class Row:
    line: int
    full_name: str
    raw_name: str | None
    phone: str | None
    phone_raw: str | None
    source: str
    course_id: uuid.UUID | None
    comment: str | None
    needs_review: bool
    skip: str | None = None
    duplicates: list[dict[str, Any]] = field(default_factory=list)


def build_rows(
    header: list[str],
    table: list[list[str]],
    mapping: dict[str, str | None],
    *,
    default_source: str,
    default_course: uuid.UUID | None,
    courses: dict[str, uuid.UUID],
) -> list[Row]:
    """Normalise every row. A row with no name and no phone is skipped, never guessed."""
    index = {h: i for i, h in enumerate(header)}

    def cell(row: list[str], fld: str) -> str:
        col = mapping.get(fld)
        i = index.get(col) if col else None
        return (row[i] if i is not None and i < len(row) else "")[:MAX_CELL].strip()

    out: list[Row] = []
    for n, row in enumerate(table, start=2):
        raw = cell(row, "full_name") or " ".join(
            x for x in (cell(row, "first_name"), cell(row, "last_name")) if x
        )
        phone, phone_raw = phone_parts(cell(row, "phone"))
        if not raw and not phone:
            out.append(Row(n, "", None, None, None, default_source, None, None, False, "empty"))
            continue
        cleaned = clean_name(raw)
        # a missing name is a row for a human, not a clean one
        review = cleaned.needs_review or not raw
        out.append(
            Row(
                line=n,
                full_name=cleaned.name,
                raw_name=raw or None,
                phone=phone,
                phone_raw=phone_raw,
                source=source_of(cell(row, "source"), default_source),
                course_id=courses.get(cell(row, "course").lower()) or default_course,
                comment=neutral(cell(row, "comment")),
                needs_review=review,
            )
        )
    return out
