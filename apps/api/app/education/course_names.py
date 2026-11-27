"""A course name holds no intake date: «Программирование», not «Программирование (23 янв)».
The date belongs to the cohort (its start date shows in the cohort title).

Only a trailing parenthesised date counts: a day with a Russian month (short or full, optional dot
and year) or a numeric dd.mm / dd.mm.yy / dd.mm.yyyy. Other brackets stay: «Python (базовый)».
Migration 0033 keeps its own frozen copy of this pattern.
"""

import re

_MONTH = (
    r"(?:янв(?:ар[ья])?|фев(?:рал[ья])?|мар(?:та?)?|апр(?:ел[ья])?|ма[йя]|июн[ья]?|июл[ья]?"
    r"|авг(?:уста?)?|сен(?:т(?:ябр[ья])?)?|окт(?:ябр[ья])?|ноя(?:бр[ья])?|дек(?:абр[ья])?)\.?"
)
_YEAR = r"(?:\s*(?:\d{4}|\d{2})(?:\s*г\.?)?)?"
_WORD_DATE = rf"\d{{1,2}}\s*{_MONTH}{_YEAR}"
# two digits each, so a version like «(3.11)» is not taken for a date
_NUM_DATE = r"(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])(?:\.(?:\d{4}|\d{2}))?"
TRAILING_DATE = re.compile(rf"\s*\(\s*(?:{_WORD_DATE}|{_NUM_DATE})\s*\)\s*$", re.IGNORECASE)


def tidy(name: str) -> str:
    """Trimmed, inner runs of spaces collapsed to one."""
    return re.sub(r"\s+", " ", name).strip()


def has_date(name: str) -> bool:
    return TRAILING_DATE.search(name) is not None


def without_date(name: str) -> str:
    """The name with a trailing «(23 янв)» removed, tidied."""
    return tidy(TRAILING_DATE.sub("", name))
