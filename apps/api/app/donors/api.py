"""Donors (Настройки → Доноры) and the donor report.

Rights: the list for choosing (cohort form, filters) needs view on `donors`, `cohorts`, `students`
or `graduates` (an instructor gets the donors of their own cohorts only); the directory with notes
and the report need `donors` view; add / edit / archive `donors` change (never the instructor
role). Donors are shared by both branches; the report counts only the cohorts the user may see
(branch scope). Numbers come from `app.metrics.donors`.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.core import clock
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.education.scope import cohort_filters, is_instructor, require_any, writer
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.metrics.donors import donor_report, donor_totals
from app.models import Cohort, CohortDonor, Donor, Enrollment

router = APIRouter(
    prefix="/api/v1/donors", tags=["donors"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("donors", "view")]
Change = Annotated[Principal, writer("donors")]
Picker = Annotated[Principal, require_any("donors", "cohorts", "students", "graduates")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DonorIn(Strict):
    name: Name
    note: Note | None = None


class DonorUpdate(Strict):
    name: Name | None = None
    note: Note | None = None
    archived: bool | None = None


def _out(d: Donor, cohorts: int = 0, students: int = 0) -> dict[str, Any]:
    return {
        "id": d.id,
        "version": d.version,
        "name": d.name,
        "note": d.note,
        "archived": d.archived,
        "cohorts": cohorts,
        "students": students,
        "created_at": d.created_at,
    }


def _snapshot(d: Donor) -> dict[str, Any]:
    return {"name": d.name, "note": d.note, "archived": d.archived}


async def _usage(
    db: AsyncSession, ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Cohorts and students (all branches) of each donor: how much it is used."""
    if not ids:
        return {}, {}
    cohorts = await db.execute(
        select(CohortDonor.donor_id, func.count())
        .where(CohortDonor.donor_id.in_(ids))
        .group_by(CohortDonor.donor_id)
    )
    students = await db.execute(
        select(Enrollment.donor_id, func.count())
        .where(Enrollment.donor_id.in_(ids))
        .group_by(Enrollment.donor_id)
    )
    return dict(cohorts.all()), dict(students.all())  # type: ignore[arg-type]


async def _load(db: AsyncSession, donor_id: uuid.UUID) -> Donor:
    donor = (await db.execute(select(Donor).where(Donor.id == donor_id))).scalar_one_or_none()
    if donor is None:
        raise DomainError(NOT_FOUND)
    return donor


async def _detail(db: AsyncSession, donor: Donor) -> dict[str, Any]:
    cohorts, students = await _usage(db, [donor.id])
    return _out(donor, cohorts.get(donor.id, 0), students.get(donor.id, 0))


def _ordered(archived: bool | None) -> Any:
    query = select(Donor).order_by(Donor.archived, Donor.name)
    if archived is not None:
        query = query.where(Donor.archived == archived)
    return query


@router.get("")
async def list_donors(p: View, db: DB, archived: bool | None = None) -> list[dict[str, Any]]:
    donors = list((await db.execute(_ordered(archived))).scalars())
    cohorts, students = await _usage(db, [d.id for d in donors])
    return [_out(d, cohorts.get(d.id, 0), students.get(d.id, 0)) for d in donors]


@router.get("/options")
async def donor_options(p: Picker, db: DB) -> list[dict[str, Any]]:
    """Every donor by name (archived last, flagged): the choices of the cohort form and filters.
    An instructor gets only the donors of their own cohorts, not the whole list."""
    query = select(Donor.id, Donor.name, Donor.archived).order_by(Donor.archived, Donor.name)
    if is_instructor(p):
        own = select(Cohort.id).where(*cohort_filters(p))
        query = query.where(
            Donor.id.in_(select(CohortDonor.donor_id).where(CohortDonor.cohort_id.in_(own)))
        )
    rows = await db.execute(query)
    return [{"id": i, "name": n, "archived": a} for i, n, a in rows.all()]


DONOR_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Донор", lambda d: d["name"]),
    Col("Заметка", lambda d: d["note"]),
    Col("В архиве", lambda d: d["archived"], "bool"),
    Col("Потоков", lambda d: d["cohorts"], "int"),
    Col("Студентов", lambda d: d["students"], "int"),
]


@router.get("/export")
async def export_donors(p: View, db: DB, archived: bool | None = None) -> Response:
    donors = list((await db.execute(_ordered(archived).limit(MAX_ROWS + 1))).scalars())
    check_cap(donors)
    cohorts, students = await _usage(db, [d.id for d in donors])
    return await xlsx_response(
        db,
        p,
        entity="donor",
        slug="donory",
        title="Доноры",
        columns=DONOR_COLUMNS,
        rows=[_out(d, cohorts.get(d.id, 0), students.get(d.id, 0)) for d in donors],
        filters={"archived": archived},
    )


@router.post("", status_code=201)
async def create_donor(body: DonorIn, p: Change, db: DB) -> dict[str, Any]:
    donor = Donor(name=body.name, note=body.note or None)
    db.add(donor)
    await db.flush()
    await db.refresh(donor)
    await record(db, p.id, "donor.create", "donor", donor.id, diff_of({}, _snapshot(donor)))
    return _out(donor)


@router.patch("/{donor_id}")
async def update_donor(
    donor_id: uuid.UUID, body: DonorUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    """Rename, change the note, archive (no longer offered for new cohorts) or bring back."""
    donor = await _load(db, donor_id)
    await check_version(
        db,
        donor,
        version,
        "donor",
        lambda: _detail(db, donor),
        changes=body.model_dump(exclude_unset=True),
    )
    before = _snapshot(donor)
    sent = body.model_fields_set
    if "name" in sent and body.name is not None:
        donor.name = body.name
    if "note" in sent:
        donor.note = body.note or None
    if "archived" in sent and body.archived is not None:
        donor.archived = body.archived
    donor.updated_at = clock.now()
    await db.flush()
    diff = diff_of(before, _snapshot(donor))
    if diff:
        action = "donor.update"
        if set(diff) == {"archived"}:
            action = "donor.archive" if donor.archived else "donor.unarchive"
        await record(db, p.id, action, "donor", donor.id, diff)
    return await _detail(db, donor)


# ---- report ------------------------------------------------------------------------------


def _report_where(p: Principal, branch_id: uuid.UUID | None) -> list[Any]:
    where: list[Any] = list(cohort_filters(p))
    if branch_id:
        p.check_scope(branch_id)
        where.append(Cohort.branch_id == branch_id)
    return where


@router.get("/report")
async def report(
    p: View, db: DB, donor_id: uuid.UUID | None = None, branch_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """«По донорам»: donor → cohorts → enrolled / studying / expelled / graduated / employed."""
    rows = await donor_report(db, _report_where(p, branch_id), donor_id)
    return {"items": rows, "donors": donor_totals(rows)}


REPORT_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Донор", lambda r: r["donor_name"]),
    Col("Поток", lambda r: r["cohort_code"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Начало", lambda r: r["start_date"], "date"),
    Col("Конец", lambda r: r["end_date"], "date"),
    Col("Статус потока", lambda r: r["cohort_status"]),
    Col("Зачислено", lambda r: r["enrolled"], "int"),
    Col("Учится", lambda r: r["studying"], "int"),
    Col("Завершили", lambda r: r["completed"], "int"),
    Col("Отчислено", lambda r: r["expelled"], "int"),
    Col("Выпустилось", lambda r: r["graduated"], "int"),
    Col("Трудоустроено", lambda r: r["employed"], "int"),
]


@router.get("/report/export")
async def export_report(
    p: View, db: DB, donor_id: uuid.UUID | None = None, branch_id: uuid.UUID | None = None
) -> Response:
    rows = await donor_report(db, _report_where(p, branch_id), donor_id)
    check_cap(rows)
    name = None
    if donor_id is not None:
        name = (await db.execute(select(Donor.name).where(Donor.id == donor_id))).scalar()
    return await xlsx_response(
        db,
        p,
        entity="donor_report",
        slug="po_donoram",
        title="По донорам",
        columns=REPORT_COLUMNS,
        rows=rows,
        filters={"donor": name, "branch_id": branch_id},
    )
