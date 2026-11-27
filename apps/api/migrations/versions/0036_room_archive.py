"""room archive: `room.archived_at`, two live cohorts moved, import placeholders archived

An archived room is hidden from the room lists, the cohort pickers and the week grid (old cohorts
and lessons keep it). The data part, decided by the owner:
- cohort G-190 moves to «Lovelace», G-270 to «Turing» (rooms of the cohort's own branch, exact
  name): cohort.room_id and the room of its lessons ahead; past lessons keep their room. The
  room EXCLUDE constraint (lesson_room_no_overlap) aborts the migration on any overlap, so a
  clash fails loudly instead of being skipped. A missing cohort or room (test databases) is
  skipped;
- every «Без аудитории (…)» room (the importer's per-cohort placeholders) with no live lesson
  ahead is archived.
Audit entries are written as «Система» (no user). Plain SQL: migrations do not import app code.
"""

import json
import logging
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"

log = logging.getLogger("alembic.runtime.migration")

MOVES = {"G-190": "Lovelace", "G-270": "Turing"}
PLACEHOLDER = "Без аудитории (%"


def _audit(
    conn: sa.Connection, action: str, entity: str, row_id: Any, label: str, branch: Any, diff: dict
) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO audit_log (user_id, action, entity, entity_id, branch_id, label, diff) "
            "VALUES (NULL, :action, :entity, :id, :branch, :label, CAST(:diff AS jsonb))"
        ),
        {
            "action": action,
            "entity": entity,
            "id": str(row_id),
            "branch": branch,
            "label": label,
            "diff": json.dumps(diff),
        },
    )


def upgrade() -> None:
    op.execute("ALTER TABLE room ADD COLUMN archived_at timestamptz")
    conn = op.get_bind()

    for code, room_name in MOVES.items():
        row = conn.execute(
            sa.text(
                "SELECT h.id, h.branch_id, h.room_id AS old, r.id AS new FROM cohort h "
                "JOIN room r ON r.branch_id = h.branch_id AND r.name = :room WHERE h.code = :code"
            ),
            {"code": code, "room": room_name},
        ).first()
        if row is None or row.old == row.new:
            log.info("room archive: %s -> %s skipped (not found or already there)", code, room_name)
            continue
        conn.execute(
            sa.text("UPDATE cohort SET room_id = :new, updated_at = now() WHERE id = :id"),
            {"new": row.new, "id": row.id},
        )
        # an overlap in the new room violates lesson_room_no_overlap and aborts the migration
        moved = conn.execute(
            sa.text(
                "UPDATE lesson SET room_id = :new WHERE cohort_id = :id AND room_id = :old "
                "AND starts_at > now()"
            ),
            {"new": row.new, "id": row.id, "old": row.old},
        ).rowcount
        _audit(
            conn,
            "cohort.update",
            "cohort",
            row.id,
            code,
            row.branch_id,
            {"room_id": [str(row.old), str(row.new)], "lessons_moved": [None, moved]},
        )
        log.info("room archive: %s -> %s, %d lessons ahead moved", code, room_name, moved)

    archived = conn.execute(
        sa.text(
            "UPDATE room SET archived_at = now() WHERE name LIKE :p AND archived_at IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM lesson l WHERE l.room_id = room.id "
            "AND l.starts_at > now() AND NOT l.cancelled) RETURNING id, name, branch_id"
        ),
        {"p": PLACEHOLDER},
    ).all()
    for room_id, name, branch_id in archived:
        _audit(conn, "room.archive", "room", room_id, name, branch_id, {"archived": [False, True]})
    log.info("room archive: %d placeholder rooms archived", len(archived))


def downgrade() -> None:
    # the cohort moves are not reverted: their lessons ahead stay in the named rooms
    op.execute("ALTER TABLE room DROP COLUMN archived_at")
