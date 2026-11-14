"""A grading scheme as an Excel file: the template and the reading of an uploaded one.

Template (one sheet): columns Категория · Баллы · Тип (авто / вручную), one row per category,
then the rows «Проходной балл», «Удержание %», «Посещаемость %», «Проходные %» with the number in
«Баллы». The same file comes back filled in: `read_scheme` turns it into a preview («понял так»)
with a Russian message per problem and per row; nothing is written until the user confirms and
the web sends the scheme through the usual PATCH (same rules, version check, audit).

The file is read with the hardened reader of the journal import (size cap while streaming, zip
bomb check, read-only / cached values: a formula is never calculated, row and column caps), text
is cut to a sane length, control characters (NUL included) are refused, and an apostrophe that
our own export put before a formula-like name is taken off again.
"""

import re
from io import BytesIO
from typing import Any

from openpyxl.utils import get_column_letter

from app.attendance import journal as jr
from app.core.errors import DomainError
from app.export import Col
from app.grading import schemes as sc
from app.leads.errors import IMPORT_NO_ROWS, IMPORT_TOO_MANY_ROWS, IMPORT_UNREADABLE
from app.metrics import grading as g

FORMULA_COLS = 20  # the three columns sit at the left
MAX_ROWS = 60  # a scheme has at most 12 categories and 4 settings: anything bigger is not one
KIND_TEXT = {g.ATTENDANCE: "авто", g.MANUAL: "вручную"}
_KINDS = {
    "авто": g.ATTENDANCE,
    "автоматически": g.ATTENDANCE,
    "auto": g.ATTENDANCE,
    "attendance": g.ATTENDANCE,
    "вручную": g.MANUAL,
    "ручной": g.MANUAL,
    "ручная": g.MANUAL,
    "manual": g.MANUAL,
}
SETTINGS = {
    "проходной балл": "pass_score",
    "удержание %": "target_retention",
    "посещаемость %": "target_attendance",
    "проходные %": "target_pass_rate",
}
SETTING_LABELS = {v: k[:1].upper() + k[1:] for k, v in SETTINGS.items()}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_FORMULA = ("=", "+", "-", "@")

COLUMNS: list[Col[tuple[str, int, str]]] = [
    Col("Категория", lambda r: r[0]),
    Col("Баллы", lambda r: r[1], "int"),
    Col("Тип", lambda r: r[2]),
]


def template_rows(scheme: g.Scheme) -> list[tuple[str, int, str]]:
    rows = [(c.name, c.weight, KIND_TEXT[c.kind]) for c in scheme.categories]
    rows += [(SETTING_LABELS[f], getattr(scheme, f), "") for f in sc.FIELDS]
    return rows


def _label(text: str) -> str:
    return re.sub(r"\s*%\s*$", " %", re.sub(r"\s+", " ", text.strip().lower()))


def _text(cell: jr.Cell) -> str:
    if cell is None:
        return ""
    s = cell.isoformat() if not isinstance(cell, str) else cell
    if s.startswith("'") and s[1:2] in _FORMULA:
        s = s[1:]  # our own export's neutralising apostrophe
    return s.strip()


def _number(raw: str) -> int | None:
    t = raw.replace(",", ".").strip()
    if not re.fullmatch(r"\d{1,3}(\.0+)?", t):
        return None
    n = int(float(t))
    return n if 0 <= n <= 100 else None


def _formulas(data: bytes) -> set[tuple[int, int]]:
    """(row 1-based, column 0-based) of the formula cells of the first sheet. The values are read
    cached (`data_only`): a formula without a cached value would read as empty, so it is named
    instead. Called after the zip check of `_read_xlsx`; never calculates anything."""
    from openpyxl import load_workbook

    found: set[tuple[int, int]] = set()
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=False)
        try:
            ws = wb[wb.sheetnames[0]]
            for r, cells in enumerate(
                ws.iter_rows(min_row=1, max_row=MAX_ROWS + 1, max_col=FORMULA_COLS), start=1
            ):
                for c, cell in enumerate(cells):
                    if getattr(cell, "data_type", None) == "f":
                        found.add((r, c))
        finally:
            wb.close()
    except Exception:  # noqa: BLE001 - unreadable here = unreadable for `_read_xlsx` already
        raise DomainError(IMPORT_UNREADABLE) from None
    return found


def _table(data: bytes) -> tuple[list[list[jr.Cell]], set[tuple[int, int]]]:
    formulas: set[tuple[int, int]] = set()
    if data[:2] == b"PK":
        _, tables = jr._read_xlsx(data, None)  # the shared hardened reader
        if not tables:
            raise DomainError(IMPORT_UNREADABLE)
        rows = tables[0].rows
        if len(rows) <= MAX_ROWS:
            formulas = _formulas(data)
    else:
        if b"\x00" in data:
            raise DomainError(IMPORT_UNREADABLE)
        rows = jr._read_csv(data).rows
    if len(rows) > MAX_ROWS:
        raise DomainError(IMPORT_TOO_MANY_ROWS, limit=MAX_ROWS)
    return rows, formulas


def _columns(rows: list[list[jr.Cell]]) -> tuple[int, tuple[int, int, int]]:
    """(first data row, (category, points, kind) columns): the «Категория» header row when there
    is one, else the first three columns from the top."""
    for r, row in enumerate(rows[:10]):
        heads = [_text(c).lower() for c in row]
        if "категория" in heads:
            cat = heads.index("категория")
            pts = next((i for i, h in enumerate(heads) if h.startswith("балл")), cat + 1)
            kind = next((i for i, h in enumerate(heads) if h.startswith("тип")), cat + 2)
            return r + 1, (cat, pts, kind)
    return 0, (0, 1, 2)


def read_scheme(data: bytes) -> dict[str, Any]:
    """The preview: categories and settings as understood, the problems (row = the line in the
    file, None = the scheme as a whole) and `ok` when it can be applied."""
    rows, formulas = _table(data)
    start, (cat, pts, kind_col) = _columns(rows)
    categories: list[dict[str, Any]] = []
    settings: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    seen: dict[str, int] = {}

    def cell(row: list[jr.Cell], i: int) -> str:
        return _text(row[i]) if i < len(row) else ""

    for r, row in enumerate(rows[start:], start=start + 1):
        name, raw_points, raw_kind = cell(row, cat), cell(row, pts), cell(row, kind_col)
        in_formula = sorted(c for c in (cat, pts, kind_col) if (r, c) in formulas)
        if in_formula:
            for c in in_formula:
                errors.append(
                    {
                        "row": r,
                        "message": "Формулы не поддерживаются — вставьте значения "
                        f"(ячейка {get_column_letter(c + 1)}{r})",
                    }
                )
            continue
        if not (name or raw_points or raw_kind):
            continue
        if _CONTROL.search(name + raw_points + raw_kind):
            errors.append({"row": r, "message": f"Строка {r}: недопустимые символы"})
            continue
        if not name:
            errors.append({"row": r, "message": f"Строка {r}: нет названия категории"})
            continue
        points = _number(raw_points)
        setting = SETTINGS.get(_label(name))
        if setting:
            if points is None:
                errors.append(
                    {
                        "row": r,
                        "message": f"Строка {r}: «{name}» — нужно целое число от 0 до 100, "
                        f"а не «{raw_points[:20]}»",
                    }
                )
            else:
                settings[setting] = points
            continue
        if len(name) > sc.NAME_MAX:
            errors.append(
                {"row": r, "message": f"Строка {r}: название длиннее {sc.NAME_MAX} символов"}
            )
            continue
        kind = _KINDS.get(raw_kind.strip().lower())
        bad = False
        if points is None:
            errors.append(
                {
                    "row": r,
                    "message": f"Строка {r}: баллы «{raw_points[:20]}» — нужно целое число "
                    "от 0 до 100",
                }
            )
            bad = True
        if kind is None:
            errors.append(
                {
                    "row": r,
                    "message": f"Строка {r}: тип «{raw_kind[:20]}» — нужно «авто» или «вручную»",
                }
            )
            bad = True
        low = name.lower()
        if low in seen:
            errors.append(
                {
                    "row": r,
                    "message": f"Строка {r}: категория «{name}» уже есть в строке {seen[low]}",
                }
            )
            bad = True
        seen.setdefault(low, r)
        if not bad:
            assert points is not None and kind is not None
            categories.append({"row": r, "name": name, "weight": points, "kind": kind})
    if not categories and not errors:
        raise DomainError(IMPORT_NO_ROWS)
    if categories:
        # whole-scheme rules (sum, one attendance, manual from 1); duplicates are already
        # reported per row and left out of `categories`
        errors += [
            {"row": None, "message": m}
            for m in sc.problems([(c["name"], c["weight"], c["kind"]) for c in categories])
        ]
    return {
        "categories": categories,
        **{f: settings.get(f) for f in sc.FIELDS},
        "sum": sum(c["weight"] for c in categories),
        "errors": errors,
        "ok": not errors,
    }
