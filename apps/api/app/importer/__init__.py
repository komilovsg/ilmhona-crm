"""Import from the old system: `python -m app.importer <snapshot.json> --dry-run | --apply`.

Rules and mappings: docs/IMPORT.md. `--dry-run` runs the whole import in a transaction, rolls it
back and writes the report; `--apply` does the same in one transaction and commits it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.importer.engine import Importer, Snapshot
from app.importer.report import Report

TABLE_OF_SHEET = {
    "STUDENTS": "student",
    "ENROLLMENTS": "enrollment",
    "PAYMENTS": "payment",
    "LEADS": "lead",
    "COHORTS": "cohort",
    "INSTRUCTORS": "app_user",
}


async def run_import(
    db: AsyncSession, snapshot: Snapshot, *, apply: bool, source: str = ""
) -> Report:
    """The whole import in one transaction on `db` (which must not be in one yet)."""
    report = Report(source=source, mode="apply" if apply else "dry-run")
    try:
        await Importer(db, snapshot, report).run()
        if apply:
            await record(
                db,
                None,
                "import.apply",
                "import",
                None,
                {t: [0, report.imported[s]] for s, t in TABLE_OF_SHEET.items()},
                label="перенос из старой системы",
            )
            await db.commit()
        else:
            await db.rollback()
    except BaseException:
        await db.rollback()
        raise
    return report
