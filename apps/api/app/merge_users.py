"""`python -m app.cli merge-users --from A --into B [--dry-run]`: one person, two accounts.

Every foreign key that points at app_user(id) is read from pg_catalog, so a table added later
is merged too. The runtime role has no DDL: the work is plain SELECT/UPDATE. `version` columns
need no manual bump, the bump_version trigger moves them on any real change of a row.
"""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.permissions import SUPERADMIN_CODE

# Tables whose user columns stay on the source: the audit trail and the sign-in history must keep
# saying who really did or tried what, and the source's own per-user settings are not data of the
# target.
KEPT_TABLES = frozenset(
    {
        "audit_log",
        "refresh_token",
        "login_attempt",
        "login_ip_attempt",
        "password_reset_request",
        "user_pref",
    }
)


class MergeError(Exception):
    pass


@dataclass
class Column:
    table: str
    column: str
    moved: bool
    count: int = 0


@dataclass
class Conflict:
    table: str
    constraint: str
    count: int


@dataclass
class Plan:
    source: str
    target: str
    columns: list[Column] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    both: dict[str, int] = field(default_factory=dict)
    has_teaches: bool = False
    sessions: int = 0


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


_FK_SQL = """
SELECT cl.relname AS tbl, a.attname AS col
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = current_schema()
CROSS JOIN LATERAL unnest(c.conkey) AS k(attnum)
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
WHERE c.contype = 'f' AND c.confrelid = 'app_user'::regclass
ORDER BY 1, 2
"""

# unique indexes (constraints included) that contain the column: the other key columns and the
# partial-index predicate, if any; `expr` marks an expression index this check cannot read
_UNIQUE_SQL = """
SELECT i.relname AS name, (x.indexprs IS NOT NULL) AS expr,
       pg_get_expr(x.indpred, x.indrelid) AS pred,
       (SELECT coalesce(array_agg(a.attname ORDER BY a.attnum), '{}')
          FROM unnest(x.indkey) AS k(attnum)
          JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum
         WHERE a.attname <> :col) AS others
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = current_schema()
WHERE x.indisunique AND t.relname = :tbl
  AND EXISTS (SELECT 1 FROM unnest(x.indkey) AS k(attnum)
              JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum
              WHERE a.attname = :col)
"""


async def _count(db: AsyncSession, sql: str, **params: object) -> int:
    return int((await db.execute(text(sql), params)).scalar_one())


@dataclass
class User:
    """Plain SQL, not the ORM entity: a dry run must work before the `teaches` column exists."""

    id: UUID
    login: str
    is_active: bool
    role_id: UUID


async def _find_user(db: AsyncSession, login: str, role: str) -> User:
    row = (
        await db.execute(
            text("SELECT id, login, is_active, role_id FROM app_user WHERE login = :l"),
            {"l": login},
        )
    ).first()
    if row is None:
        raise MergeError(f"{role} user {login!r} not found")
    return User(*row)


async def build_plan(db: AsyncSession, source: User, target: User) -> Plan:
    plan = Plan(source.login, target.login)
    params = {"s": source.id, "t": target.id}
    for row in (await db.execute(text(_FK_SQL))).all():
        tbl, col = row
        moved = tbl not in KEPT_TABLES
        count = await _count(db, f"SELECT count(*) FROM {_q(tbl)} WHERE {_q(col)} = :s", **params)
        plan.columns.append(Column(tbl, col, moved, count))
    moved_cols = [c for c in plan.columns if c.moved]
    for c in moved_cols:
        if not c.count:
            continue
        for name, expr, pred, others in (
            await db.execute(text(_UNIQUE_SQL), {"tbl": c.table, "col": c.column})
        ).all():
            if expr:
                raise MergeError(f"{c.table}.{name}: expression unique index, cannot be checked")
            same = "".join(f" AND t.{_q(o)} = s.{_q(o)}" for o in others)
            where = f" AND ({pred})" if pred else ""
            n = await _count(
                db,
                f"SELECT count(*) FROM {_q(c.table)} s WHERE s.{_q(c.column)} = :s{where} "
                f"AND EXISTS (SELECT 1 FROM {_q(c.table)} t WHERE t.{_q(c.column)} = :t{same})",
                **params,
            )
            if n:
                plan.conflicts.append(Conflict(c.table, name, n))
    by_table: dict[str, list[str]] = {}
    for c in moved_cols:
        by_table.setdefault(c.table, []).append(c.column)
    for tbl, cols in by_table.items():
        if len(cols) < 2:
            continue
        has_s = " OR ".join(f"{_q(c)} = :s" for c in cols)
        has_t = " OR ".join(f"{_q(c)} = :t" for c in cols)
        n = await _count(
            db, f"SELECT count(*) FROM {_q(tbl)} WHERE ({has_s}) AND ({has_t})", **params
        )
        if n:
            plan.both[tbl] = n
    plan.has_teaches = bool(
        await _count(
            db,
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = 'app_user' AND column_name = 'teaches'",
        )
    )
    plan.sessions = await _count(
        db,
        "SELECT count(*) FROM refresh_token WHERE user_id = :s AND revoked_at IS NULL",
        s=source.id,
    )
    return plan


async def check_refusals(db: AsyncSession, source: User, target: User) -> None:
    if source.id == target.id:
        raise MergeError("--from and --into are the same user")
    if not target.is_active:
        raise MergeError(f"target {target.login!r} is inactive")
    if source.is_active:
        others = await _count(
            db,
            "SELECT count(*) FROM app_user u JOIN role r ON r.id = u.role_id "
            "WHERE r.code = :code AND u.is_active AND u.id <> :s",
            code=SUPERADMIN_CODE,
            s=source.id,
        )
        is_super = await _count(
            db,
            "SELECT count(*) FROM role WHERE id = :r AND code = :code",
            r=source.role_id,
            code=SUPERADMIN_CODE,
        )
        if is_super and not others:
            raise MergeError(f"{source.login!r} is the last active superadmin")


def render(plan: Plan, dry_run: bool) -> str:
    lines = [
        f"merge {plan.source} -> {plan.target}"
        + (" (dry run, nothing written)" if dry_run else ""),
        f"{'table.column':<44}{'rows':>7}  action",
    ]
    for c in plan.columns:
        lines.append(
            f"{c.table + '.' + c.column:<44}{c.count:>7}  {'moved' if c.moved else 'kept'}"
        )
    moved = sum(c.count for c in plan.columns if c.moved)
    lines.append(f"total rows to move: {moved}")
    for tbl, n in plan.both.items():
        lines.append(f"rows with both accounts: {tbl} {n}")
    lines.append(f"source sessions to revoke: {plan.sessions}")
    lines.append(
        f"{plan.source}: is_active -> false, teaches -> false; {plan.target}: teaches -> true"
        if plan.has_teaches
        else f"teaches column absent; {plan.source}: is_active -> false"
    )
    for k in plan.conflicts:
        lines.append(f"CONFLICT {k.table} {k.constraint}: {k.count} rows")
    return "\n".join(lines)


async def merge_users(db: AsyncSession, source_login: str, target_login: str, dry_run: bool) -> str:
    """Report text; raises MergeError to refuse. Real run: the caller commits the session."""
    source = await _find_user(db, source_login, "source")
    target = await _find_user(db, target_login, "target")
    await check_refusals(db, source, target)
    plan = await build_plan(db, source, target)
    report = render(plan, dry_run)
    if plan.conflicts:
        raise MergeError(report + "\naborted: unique conflicts, nothing changed")
    if dry_run:
        return report
    if not plan.has_teaches:
        raise MergeError("teaches column absent: deploy migration 0020 first")
    params = {"s": source.id, "t": target.id}
    for c in plan.columns:
        if c.moved and c.count:
            await db.execute(
                text(f"UPDATE {_q(c.table)} SET {_q(c.column)} = :t WHERE {_q(c.column)} = :s"),
                params,
            )
    await db.execute(
        text(
            "UPDATE refresh_token SET revoked_at = now() WHERE user_id = :s AND revoked_at IS NULL"
        ),
        params,
    )
    await db.execute(
        text("UPDATE app_user SET is_active = false, teaches = false WHERE id = :s"), params
    )
    await db.execute(text("UPDATE app_user SET teaches = true WHERE id = :t"), params)
    moved = {f"{c.table}.{c.column}": c.count for c in plan.columns if c.moved and c.count}
    await record(
        db,
        target.id,
        "user.merge",
        "app_user",
        source.id,
        {
            "is_active": [True, False],
            "merged_into": [None, target.login],
            "moved": [None, moved],
            "cli": [None, True],
        },
        label=source.login,
    )
    return report
