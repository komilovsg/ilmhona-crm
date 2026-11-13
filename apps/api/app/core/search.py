"""The one text-search helper: every list search goes through `search_clause`.

- Names and other text: case-insensitive, `ё` equals `е`; `%`, `_` and `\\` in the term are literal.
- Phones: a term with at least 3 digits also matches the phone's digits only, so
  `+992 90 123 45 06`, `(90) 123` and `90123` all find `+992901234506`.
"""

import re
from typing import Any

from sqlalchemy import ColumnElement, func, or_


def fold(value: str) -> str:
    return value.strip().lower().replace("ё", "е")


def like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def folded(column: Any) -> ColumnElement[str]:
    return func.translate(func.lower(column), "ё", "е")


def search_clause(
    q: str, texts: tuple[Any, ...], phones: tuple[Any, ...] = ()
) -> ColumnElement[bool]:
    pattern = like_pattern(fold(q))
    terms: list[ColumnElement[bool]] = [folded(c).like(pattern) for c in texts]
    digits = re.sub(r"\D", "", q)
    if len(digits) >= 3:
        terms += [func.regexp_replace(c, r"\D", "", "g").like(f"%{digits}%") for c in phones]
    # a phone is also matched as typed («+992 90»)
    terms += [folded(c).like(pattern) for c in phones]
    return or_(*terms)
