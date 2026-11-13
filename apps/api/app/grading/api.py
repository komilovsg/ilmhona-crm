"""Grading schemes: the academy standard, a cohort's own scheme, the graduation recalculation.

Rights:
- the standard: everybody signed in reads it; only the superadmin changes or imports it;
- a cohort's scheme: read with view on Потоки or Посещаемость и оценки, in scope; changed, reset
  and imported with `attendance` change in scope (the cohort's instructor for their own cohort, a
  manager for their branch, the superadmin), never on a cancelled cohort;
- graduation preview: as reading; recalculation: as changing.
Every change is versioned (`X-Record-Version`: the scheme's version; a cohort without a scheme
of its own is version 0) and audited with the points before → after.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attendance import journal as jr
from app.audit.log import record
from app.auth.deps import CurrentUser, Principal, require, require_csrf_header
from app.cohorts import status as st
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, STALE_VERSION, DomainError
from app.core.versioning import Version, _last_change, check_version
from app.education.errors import COHORT_CLOSED
from app.education.scope import check_cohort_visible, require_any
from app.export import xlsx_response
from app.grading import excel
from app.grading import schemes as sc
from app.grading.errors import COHORT_NOT_COMPLETED
from app.leads.errors import IMPORT_TOO_LARGE
from app.metrics import grading as g
from app.models import AppUser, Cohort, Enrollment, GradeScore, GradingScheme
from app.permissions import allows

router = APIRouter(prefix="/api/v1", tags=["grading"], dependencies=[Depends(require_csrf_header)])

Reader = Annotated[Principal, require_any("cohorts", "attendance")]
Change = Annotated[Principal, require("attendance", "change")]
MAX_BYTES = jr.MAX_BYTES  # the same cap as the journal and lead imports


def _superadmin(p: Principal) -> None:
    if not p.is_superadmin:
        raise DomainError(FORBIDDEN, section="grading", level="change")


async def _read_body(request: Request) -> bytes:
    """The raw file, capped while it streams in (also without Content-Length)."""
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise DomainError(IMPORT_TOO_LARGE, limit=MAX_BYTES)
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BYTES:
            raise DomainError(IMPORT_TOO_LARGE, limit=MAX_BYTES)
    return bytes(data)


async def _preview(request: Request) -> dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool

    data = await _read_body(request)
    return await run_in_threadpool(excel.read_scheme, data)


# ---- the academy standard ---------------------------------------------------------------


async def _standard_row(db: AsyncSession) -> GradingScheme:
    return (
        await db.execute(select(GradingScheme).where(GradingScheme.cohort_id.is_(None)))
    ).scalar_one()


async def _standard_payload(db: AsyncSession, p: Principal) -> dict[str, Any]:
    scheme = await g.standard_scheme(db)
    row = await _standard_row(db)
    by = (
        await db.execute(select(AppUser.full_name).where(AppUser.id == row.updated_by))
    ).scalar_one_or_none()
    own = (
        await db.execute(
            select(func.count())
            .select_from(GradingScheme)
            .where(GradingScheme.cohort_id.is_not(None))
        )
    ).scalar_one()
    return {
        "version": scheme.version,
        "scheme": sc.scheme_out(scheme),
        "can_edit": p.is_superadmin,
        "updated_at": row.updated_at,
        "updated_by_name": by,
        "cohorts_with_own": own,
    }


@router.get("/grading/standard")
async def get_standard(p: CurrentUser, db: DB) -> dict[str, Any]:
    return await _standard_payload(db, p)


@router.patch("/grading/standard")
async def update_standard(
    body: sc.SchemeIn, version: Version, p: CurrentUser, db: DB
) -> dict[str, Any]:
    _superadmin(p)
    row = await _standard_row(db)
    await check_version(db, row, version, "grading_scheme", lambda: _standard_payload(db, p))
    before = await g.standard_scheme(db)
    draft = sc.draft_of(before, body, await sc.key_names(db))
    diff = sc.change_diff(before, draft)
    if not diff:
        return await _standard_payload(db, p)
    lost = await sc.check_archive(
        db, before.categories, draft.categories, cohort_id=None, confirmed=body.confirm_archive
    )
    await sc.write(db, row, draft, p.id)
    if lost:
        diff["archived"] = [None, _archived_text(lost)]
    await record(db, p.id, "grading.standard_update", "grading_scheme", row.id, diff)
    return await _standard_payload(db, p)


@router.get("/grading/standard/template")
async def standard_template(p: CurrentUser, db: DB) -> Response:
    return await _template(db, p, await g.standard_scheme(db), "standart_ocenok", None)


@router.post("/grading/standard/import")
async def standard_import(request: Request, p: CurrentUser) -> dict[str, Any]:
    """What the uploaded file says (nothing is written; the web applies it with PATCH)."""
    _superadmin(p)
    return await _preview(request)


def _archived_text(lost: list[dict[str, Any]]) -> str:
    return ", ".join(f"{x['name']} ({x['scores']})" for x in lost)


async def _template(
    db: AsyncSession, p: Principal, scheme: g.Scheme, slug: str, cohort: Cohort | None
) -> Response:
    return await xlsx_response(
        db,
        p,
        entity="grading_scheme",
        slug=slug,
        title="Шкала оценок",
        columns=excel.COLUMNS,
        rows=excel.template_rows(scheme),
        filters={"cohort": cohort.code} if cohort else {},
    )


# ---- one cohort -------------------------------------------------------------------------


async def _cohort(
    db: AsyncSession, p: Principal, cohort_id: uuid.UUID, *, lock: bool = False
) -> Cohort:
    query = select(Cohort).where(Cohort.id == cohort_id)
    if lock:
        query = query.with_for_update()
    cohort = (await db.execute(query)).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)
    return cohort


def _writable(cohort: Cohort) -> None:
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)


async def _archived(
    db: AsyncSession, cohort_id: uuid.UUID, scheme: g.Scheme
) -> list[dict[str, Any]]:
    """Scores entered in the cohort for categories its scheme does not have (kept, not counted)."""
    live = {c.key for c in scheme.manual}
    rows = (
        await db.execute(
            select(GradeScore.category_key, func.count())
            .join(Enrollment, Enrollment.id == GradeScore.enrollment_id)
            .where(Enrollment.cohort_id == cohort_id, GradeScore.category_key.not_in(live))
            .group_by(GradeScore.category_key)
            .order_by(GradeScore.category_key)
        )
    ).all()
    if not rows:
        return []
    names = await sc.key_names(db)
    return [{"key": k, "name": names.get(k, k), "scores": n} for k, n in rows]


async def _cohort_payload(db: AsyncSession, p: Principal, cohort: Cohort) -> dict[str, Any]:
    own = await g.own_scheme(db, cohort.id)
    scheme = own or await g.standard_scheme(db)
    return {
        "cohort_id": cohort.id,
        "cohort_code": cohort.code,
        "source": scheme.source,
        "version": own.version if own else 0,
        "scheme": sc.scheme_out(scheme),
        "archived": await _archived(db, cohort.id, scheme),
        "can_edit": allows(p.level("attendance"), "change") and cohort.status != st.CANCELLED,
        "completed": cohort.status == st.DONE,
    }


async def _check_cohort_version(
    db: AsyncSession, p: Principal, cohort: Cohort, own: GradingScheme | None, expected: int
) -> None:
    current = own.version if own else 0
    if current != expected:
        raise DomainError(
            STALE_VERSION,
            version=current,
            current=await _cohort_payload(db, p, cohort),
            **await _last_change(db, "cohort", cohort.id),
        )


async def _own_row(db: AsyncSession, cohort_id: uuid.UUID) -> GradingScheme | None:
    return (
        await db.execute(
            select(GradingScheme).where(GradingScheme.cohort_id == cohort_id).with_for_update()
        )
    ).scalar_one_or_none()


@router.get("/cohorts/{cohort_id}/grading")
async def get_cohort_scheme(cohort_id: uuid.UUID, p: Reader, db: DB) -> dict[str, Any]:
    return await _cohort_payload(db, p, await _cohort(db, p, cohort_id))


@router.patch("/cohorts/{cohort_id}/grading")
async def update_cohort_scheme(
    cohort_id: uuid.UUID, body: sc.SchemeIn, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    """Change the cohort's own scheme; a cohort that follows the standard gets its own copy of
    it with the changes applied. Totals follow at once; statuses of a finished cohort do not."""
    cohort = await _cohort(db, p, cohort_id, lock=True)  # one scheme writer per cohort at a time
    _writable(cohort)
    row = await _own_row(db, cohort.id)
    await _check_cohort_version(db, p, cohort, row, version)
    before = await g.scheme_of(db, cohort.id)
    draft = sc.draft_of(before, body, await sc.key_names(db))
    diff = sc.change_diff(before, draft)
    if not diff:
        return await _cohort_payload(db, p, cohort)
    lost = await sc.check_archive(
        db, before.categories, draft.categories, cohort_id=cohort.id, confirmed=body.confirm_archive
    )
    if row is None:
        row = GradingScheme(cohort_id=cohort.id)
        db.add(row)
        await db.flush()
    await sc.write(db, row, draft, p.id)
    if lost:
        diff["archived"] = [None, _archived_text(lost)]
    await record(
        db,
        p.id,
        "grading.cohort_update",
        "cohort",
        cohort.id,
        diff,
        branch_id=cohort.branch_id,
        label=cohort.code,
    )
    return await _cohort_payload(db, p, cohort)


@router.delete("/cohorts/{cohort_id}/grading")
async def reset_cohort_scheme(
    cohort_id: uuid.UUID,
    version: Version,
    p: Change,
    db: DB,
    confirm_archive: bool = False,
) -> dict[str, Any]:
    """«Вернуть стандарт академии»: the cohort's own scheme goes, the standard applies again."""
    cohort = await _cohort(db, p, cohort_id, lock=True)
    _writable(cohort)
    row = await _own_row(db, cohort.id)
    await _check_cohort_version(db, p, cohort, row, version)
    if row is None:
        return await _cohort_payload(db, p, cohort)
    before = await g.scheme_of(db, cohort.id)
    standard = await g.standard_scheme(db)
    lost = await sc.check_archive(
        db, before.categories, standard.categories, cohort_id=cohort.id, confirmed=confirm_archive
    )
    await db.delete(row)
    await db.flush()
    diff = sc.change_diff(before, standard)
    if lost:
        diff["archived"] = [None, _archived_text(lost)]
    await record(
        db,
        p.id,
        "grading.cohort_reset",
        "cohort",
        cohort.id,
        diff,
        branch_id=cohort.branch_id,
        label=cohort.code,
    )
    return await _cohort_payload(db, p, cohort)


@router.get("/cohorts/{cohort_id}/grading/template")
async def cohort_template(cohort_id: uuid.UUID, p: Reader, db: DB) -> Response:
    cohort = await _cohort(db, p, cohort_id)
    scheme = await g.scheme_of(db, cohort.id)
    return await _template(db, p, scheme, f"shkala_{cohort.code}", cohort)


@router.post("/cohorts/{cohort_id}/grading/import")
async def cohort_import(
    cohort_id: uuid.UUID, request: Request, p: Change, db: DB
) -> dict[str, Any]:
    cohort = await _cohort(db, p, cohort_id)
    _writable(cohort)
    return await _preview(request)


# ---- graduation after a scheme change ---------------------------------------------------


def _changes_out(
    cohort: Cohort, changes: list[dict[str, Any]], skipped: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "completed": cohort.status == st.DONE,
        "changes": changes,
        "skipped": skipped,
        "graduates": sum(1 for c in changes if c["new_status"] == st.GRADUATE),
        "not_graduates": sum(1 for c in changes if c["new_status"] == st.COMPLETED),
    }


@router.get("/cohorts/{cohort_id}/graduation-preview")
async def graduation_preview(cohort_id: uuid.UUID, p: Reader, db: DB) -> dict[str, Any]:
    """Who would become a graduate (стал выпускником) or stop being one (перестал) by the
    current totals. Nothing is written."""
    cohort = await _cohort(db, p, cohort_id)
    return _changes_out(cohort, *await st.graduation_changes(db, cohort))


@router.post("/cohorts/{cohort_id}/graduation-recalc")
async def graduation_recalc(
    cohort_id: uuid.UUID,
    p: Change,
    db: DB,
    expected: Annotated[int | None, Query(ge=0)] = None,
) -> dict[str, Any]:
    """Apply the preview (one audit entry per student). `expected`: how many changes the user
    saw; another number means the totals moved meanwhile: 409 with the fresh preview."""
    cohort = await _cohort(db, p, cohort_id, lock=True)
    if cohort.status != st.DONE:
        raise DomainError(COHORT_NOT_COMPLETED)
    if expected is not None:
        changes, skipped = await st.graduation_changes(db, cohort)
        if len(changes) != expected:
            raise DomainError(
                STALE_VERSION, version=len(changes), current=_changes_out(cohort, changes, skipped)
            )
    return _changes_out(cohort, *await st.apply_graduation(db, cohort, p.id))
