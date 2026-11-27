"""clean course names: no intake date in a course name, dated duplicates merged

«Программирование (23 янв)», «Программирование (10 мар)» and «Программирование» become one
course «Программирование»; the date shows in the cohort title (from the cohort's start date).

Per group of courses whose names match once the trailing date is cut (trimmed, spaces collapsed,
case ignored): a group with a dated name or with more than one course (case-only twins such as
«Python» / «python» merge too):
- the survivor is the oldest course (created_at, then id); its duration, format and direction
  stay; its default price too, unless it is 0 and a merged twin's is not: then the paid twin
  with the most cohorts gives it (a tie: the highest). Cohorts keep their own price and funding.
  The merged courses' differing values are kept in the audit entry;
- every reference moves to the survivor: cohort, lead, campaign, note, certificate,
  cert_template_rule (a rule the survivor already has for that instructor wins, the merged one
  is dropped);
- the survivor takes a merged course's legacy_ref when it has none, so a re-run of the import
  finds it;
- the merged courses are deleted; the survivor keeps its own name without the date, unless that
  starts with a small letter and another course of the group is capitalised: then the
  capitalised variant with the most cohorts wins (a tie: the oldest);
- three one-off merges into «Python - базовый уровень» (ALIASES), decided by the owner;
- one audit entry per merged course («course.merge») and per rename («course.update»).

The pattern is a frozen copy of app/education/course_names.py.
"""

import json
import logging
import re
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"

log = logging.getLogger("alembic.runtime.migration")

_MONTH = (
    r"(?:янв(?:ар[ья])?|фев(?:рал[ья])?|мар(?:та?)?|апр(?:ел[ья])?|ма[йя]|июн[ья]?|июл[ья]?"
    r"|авг(?:уста?)?|сен(?:т(?:ябр[ья])?)?|окт(?:ябр[ья])?|ноя(?:бр[ья])?|дек(?:абр[ья])?"
    # the old system wrote English months: «AI в дизайне (Aug», «Frontend (Sep 26) (Sep»
    r"|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?![a-zа-яё])"
)
_YEAR = r"(?:\s*(?:\d{4}|\d{2})(?:\s*г\.?)?)?"
_WORD_DATE = rf"(?:\d{{1,2}}\s*)?{_MONTH}(?:\s*\d{{1,2}}(?!\d))?{_YEAR}"
_NUM_DATE = r"(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])(?:\.(?:\d{4}|\d{2}))?"
# one or more trailing dates; the last bracket may be open (cut off in the old system)
TRAILING_DATE = re.compile(rf"(?:\s*\(\s*(?:{_WORD_DATE}|{_NUM_DATE})\s*\)?)+\s*$", re.IGNORECASE)

# table -> the audit diff key counting its moved rows
MOVED = {
    "cohort": "cohorts",
    "lead": "leads",
    "campaign": "campaigns",
    "certificate": "certificates",
    "note": "notes",
}
FIELDS = ("direction", "default_price_month", "duration_months", "format")  # kept on survivor
NO_INSTRUCTOR = "'00000000-0000-0000-0000-000000000000'::uuid"


def _tidy(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()


def _plain(value: Any) -> Any:
    return value if value is None or isinstance(value, int | str) else str(value)


def _audit(conn: sa.Connection, action: str, entity_id: Any, label: str, diff: dict) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO audit_log (user_id, action, entity, entity_id, label, diff) "
            "VALUES (NULL, :action, 'course', :id, :label, CAST(:diff AS jsonb))"
        ),
        {"action": action, "id": str(entity_id), "label": label, "diff": json.dumps(diff)},
    )


# One-off merges decided by the owner: these cohorts' courses are the base Python course (names
# after the date is cut, compared ignoring case).
ALIASES = {
    "python - базовый уровень 1 группа": "Python - базовый уровень",
    "python - базовый уровень 2 группа": "Python - базовый уровень",
    "python - базовый уровень остатки": "Python - базовый уровень",
}


def _default_price(members: list[dict[str, Any]]) -> Any:
    """A course price is only the default for new cohorts (each cohort keeps its own price and
    funding). A free survivor takes a paid twin's price: the twin with the most cohorts, a tie:
    the highest price."""
    survivor = members[0]
    if survivor["default_price_month"] > 0:
        return survivor["default_price_month"]
    paid = [m for m in members[1:] if m["default_price_month"] > 0]
    if not paid:
        return survivor["default_price_month"]
    best = max(paid, key=lambda m: (m["cohorts"], m["default_price_month"]))
    return best["default_price_month"]


def _capitalised(name: str) -> bool:
    return name[:1].isupper()


def _final_name(members: list[dict[str, Any]]) -> str:
    """The survivor's clean name, or the capitalised variant with the most cohorts (a tie: the
    oldest; `members` come oldest first) when the survivor's starts with a small letter."""
    survivor = members[0]
    if _capitalised(survivor["clean"]):
        return str(survivor["clean"])
    proper = [m for m in members if _capitalised(m["clean"])]
    if not proper:
        return str(survivor["clean"])
    return str(max(proper, key=lambda m: m["cohorts"])["clean"])  # max keeps the first on a tie


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, name, legacy_ref, direction, default_price_month, duration_months, format, "
            "(SELECT count(*) FROM cohort h WHERE h.course_id = course.id) AS cohorts "
            "FROM course ORDER BY created_at, id"
        )
    ).mappings()
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        clean = _tidy(TRAILING_DATE.sub("", row["name"]))
        if not clean:  # a name that is only a date stays as it is
            continue
        clean = ALIASES.get(clean.casefold(), clean)
        groups.setdefault(clean.casefold(), []).append({**row, "clean": clean})

    for members in groups.values():
        if len(members) == 1 and members[0]["clean"] == members[0]["name"]:
            continue  # a single course with a clean name: nothing to do
        survivor, merged = members[0], members[1:]
        new_name = _final_name(members)
        new_price = _default_price(members)
        sid = survivor["id"]
        legacy = survivor["legacy_ref"]
        for m in merged:
            mid = m["id"]
            moved: dict[str, Any] = {"into": [None, new_name]}
            for table, key in MOVED.items():
                n = conn.execute(
                    sa.text(f"UPDATE {table} SET course_id = :s WHERE course_id = :m"),
                    {"s": sid, "m": mid},
                ).rowcount
                moved[key] = [None, n]
            conn.execute(
                sa.text(
                    "UPDATE cert_template_rule r SET course_id = :s WHERE r.course_id = :m "
                    "AND NOT EXISTS (SELECT 1 FROM cert_template_rule t WHERE t.course_id = :s "
                    f"AND coalesce(t.instructor_id, {NO_INSTRUCTOR}) = "
                    f"coalesce(r.instructor_id, {NO_INSTRUCTOR}))"
                ),
                {"s": sid, "m": mid},
            )
            differs = {
                f: [_plain(m[f]), _plain(survivor[f])] for f in FIELDS if m[f] != survivor[f]
            }
            if differs:
                moved["differs"] = differs
            if legacy is None and m["legacy_ref"] is not None:
                legacy = m["legacy_ref"]
            # its leftover template rules (the survivor already had one) go with it (CASCADE)
            conn.execute(sa.text("DELETE FROM course WHERE id = :m"), {"m": mid})
            _audit(conn, "course.merge", mid, m["name"], moved)
            log.info("course %r merged into %r: %s", m["name"], new_name, moved)
        if legacy != survivor["legacy_ref"]:
            conn.execute(
                sa.text("UPDATE course SET legacy_ref = :r WHERE id = :s"), {"r": legacy, "s": sid}
            )
        change: dict[str, Any] = {}
        if new_name != survivor["name"]:
            change["name"] = [survivor["name"], new_name]
        if new_price != survivor["default_price_month"]:
            change["default_price_month"] = [
                _plain(survivor["default_price_month"]),
                _plain(new_price),
            ]
        if change:
            conn.execute(
                sa.text("UPDATE course SET name = :n, default_price_month = :p WHERE id = :s"),
                {"n": new_name, "p": new_price, "s": sid},
            )
            _audit(conn, "course.update", sid, new_name, change)
            log.info("course %r changed: %s", survivor["name"], change)


def downgrade() -> None:
    # Data cleanup only: merged courses and the old names cannot be told apart again (the audit
    # log keeps what happened), so going down changes nothing.
    pass
