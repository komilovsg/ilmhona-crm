"""Issue and registry of certificates (stage C2).

Rights: check, issue, reissue and revoke need `certificates` change and never the instructor role
(#24); the registry, a certificate and its PDF need `certificates` view. All of it is
branch-scoped (a foreign branch is 404); an instructor sees only their own cohorts' certificates.
A certificate keeps the exact template version and a snapshot of its values; its number is the
enrollment's `certificate_no` (one numbering, see `app.graduates.numbering`).
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.audit.log import record
from app.auth.deps import Principal, require, require_csrf_header
from app.certificates.api import file_name, pick_template
from app.certificates.errors import (
    CERT_ALREADY_ISSUED,
    CERT_BATCH_FIXED,
    CERT_COMMENT_REQUIRED,
    CERT_NOT_READY,
    CERT_NOT_VALID,
    COHORT_NOT_FINISHED,
)
from app.certificates.fields import SAMPLE_CODE, load_settings
from app.certificates.issuing import (
    FIX_TEXTS,
    PLACEHOLDER_NUMBER,
    AssetCache,
    Fix,
    Prepared,
    chosen_template,
    clean_custom,
    fix_of,
    layout_of,
    new_verify_code,
    prepare,
    published_version,
    snapshot,
)
from app.certificates.render import render_pdf
from app.certificates.stored import render_certificate
from app.cohorts.status import DONE, GRADUATE
from app.core import clock
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, DomainError
from app.core.paging import Page, PageSize
from app.core.search import search_clause
from app.education.scope import is_instructor, writer
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.graduates.errors import NOT_GRADUATE
from app.graduates.numbering import assign_number
from app.models import (
    AppUser,
    Branch,
    Certificate,
    CertTemplate,
    CertTemplateVersion,
    Cohort,
    Course,
    Enrollment,
    Student,
)
from app.permissions import allows

Issuer = aliased(AppUser)
BULK_LABEL = "массовая выдача"  # in an audit label where a cohort code would stand

router = APIRouter(
    prefix="/api/v1", tags=["certificates"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("certificates", "view")]
# an instructor never issues, reissues or revokes (#24), whatever the rights matrix says
Change = Annotated[Principal, writer("certificates")]
Lang = Literal["ru", "en", "tg"]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Custom = dict[str, Annotated[str, Field(max_length=500)]]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueBatch(Body):
    template_id: uuid.UUID
    lang: Lang | None = None
    enrollment_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=500)]
    custom: Custom | None = None


class IssueOne(Body):
    template_id: uuid.UUID | None = None
    lang: Lang | None = None
    custom: Custom | None = None
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class Reissue(Body):
    comment: Reason
    template_id: uuid.UUID | None = None


class Revoke(Body):
    reason: Reason


async def _cohort(db: AsyncSession, p: Principal, cohort_id: uuid.UUID) -> tuple[Cohort, Course]:
    row = (
        await db.execute(
            select(Cohort, Course)
            .join(Course, Course.id == Cohort.course_id)
            .where(Cohort.id == cohort_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(row[0].branch_id)
    return row[0], row[1]


def _gone() -> Cohort:
    raise DomainError(NOT_FOUND)


def _finished(cohort: Cohort) -> None:
    """Certificates are issued, and reissued, only once the cohort is finished."""
    if cohort.status != DONE:
        raise DomainError(COHORT_NOT_FINISHED, status=cohort.status)


def _fix_item(enrollment_id: uuid.UUID, name: str, fix: Fix) -> dict[str, Any]:
    return {
        "enrollment_id": enrollment_id,
        "student_name": name,
        "reason": fix.code,
        "text": fix.text,
    }


# ---- check -----------------------------------------------------------------------------------


@router.get("/cohorts/{cohort_id}/certificates/check")
async def check(
    cohort_id: uuid.UUID,
    p: Change,
    db: DB,
    template_id: uuid.UUID | None = None,
    lang: Lang | None = None,
) -> dict[str, Any]:
    """Per enrollment of the cohort: `issued`, `ready` or `fix` with the reason. Writes nothing."""
    cohort, course = await _cohort(db, p, cohort_id)
    if template_id is not None:
        template = await chosen_template(db, template_id)
    else:
        template = await pick_template(db, course.id, cohort.instructor_id)
    version = await published_version(db, template)
    layout = layout_of(version)
    lang_code: str = lang or template.lang
    settings_row = await load_settings(db)
    rows = (
        await db.execute(
            select(Enrollment, Student.full_name)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.cohort_id == cohort_id)
            .order_by(Student.full_name, Enrollment.id)
        )
    ).all()
    valid = {
        c.enrollment_id: c
        for c in (
            await db.execute(
                select(Certificate).where(
                    Certificate.cohort_id == cohort_id, Certificate.status == "valid"
                )
            )
        ).scalars()
    }
    cache = AssetCache(db)
    items: list[dict[str, Any]] = []
    for enrollment, name in rows:
        item: dict[str, Any] = {
            "enrollment_id": enrollment.id,
            "student_name": name,
            "enrollment_status": enrollment.status,
            "number": enrollment.certificate_no,
            "certificate_id": None,
            "reason": None,
            "text": None,
            "score": None,
        }
        cert = valid.get(enrollment.id)
        if cert is not None:
            item.update(status="issued", number=cert.number, certificate_id=cert.id)
            items.append(item)
            continue
        prep = await prepare(db, enrollment.id, layout, lang_code, {}, cache, settings_row)
        item["score"] = float(prep.ctx.values["grade.total"])  # type: ignore[arg-type]
        fix = (
            Fix("not_graduate", FIX_TEXTS["not_graduate"])
            if enrollment.status != GRADUATE
            else fix_of(layout, prep.ctx, prep.assets)
        )
        if fix is None:
            item["status"] = "ready"
        else:
            item.update(status="fix", reason=fix.code, text=fix.text)
        items.append(item)
    return {
        "template_id": template.id,
        "template_name": template.name,
        "lang": lang_code,
        "allow_non_graduate": settings_row.allow_non_graduate,
        "items": items,
        "counts": {
            s: sum(1 for i in items if i["status"] == s) for s in ("ready", "issued", "fix")
        },
    }


@router.get("/cohorts/{cohort_id}/enrollments/{enrollment_id}/certificate/preview")
async def preview_one(
    cohort_id: uuid.UUID,
    enrollment_id: uuid.UUID,
    p: Change,
    db: DB,
    template_id: uuid.UUID | None = None,
    lang: Lang | None = None,
) -> Response:
    """The student's certificate with the template's published version and a placeholder number.
    Writes nothing: no number, no row, no audit entry."""
    cohort, course = await _cohort(db, p, cohort_id)
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.cohort_id != cohort.id:
        raise DomainError(NOT_FOUND)
    if template_id is not None:
        template = await chosen_template(db, template_id)
    else:
        template = await pick_template(db, course.id, cohort.instructor_id)
    layout = layout_of(await published_version(db, template))
    prep = await prepare(
        db, enrollment_id, layout, lang or template.lang, {}, AssetCache(db),
        await load_settings(db), number=enrollment.certificate_no or PLACEHOLDER_NUMBER,
    )  # fmt: skip
    prep.ctx.verify_code, prep.ctx.public = SAMPLE_CODE, True
    name = str(prep.ctx.values["student.full_name"])
    if fix := fix_of(layout, prep.ctx, prep.assets):
        raise DomainError(CERT_NOT_READY, items=[_fix_item(enrollment_id, name, fix)])
    pdf = await render_pdf(layout, prep.ctx, prep.assets)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="preview.pdf"'},
    )


# ---- issue -----------------------------------------------------------------------------------


async def _create(
    db: AsyncSession,
    p: Principal,
    prep: Prepared,
    template: CertTemplate,
    version: CertTemplateVersion,
    lang: str,
    custom: dict[str, str],
    comment: str | None,
    *,
    non_graduate: bool = False,
    previous: Certificate | None = None,
) -> Certificate:
    """Number the enrollment if needed, store the row and the audit entry."""
    enrollment = prep.enrollment
    await assign_number(db, enrollment, graduate_only=not non_graduate and previous is None)
    number = enrollment.certificate_no
    assert number
    enrollment.certificate_version_id = version.id  # the PDF route keeps drawing from it
    code = new_verify_code()
    cert = Certificate(
        number=number,
        verify_code=code,
        public_code=code,
        enrollment_id=enrollment.id,
        cohort_id=prep.cohort.id,
        course_id=prep.cohort.course_id,
        branch_id=prep.cohort.branch_id,
        instructor_id=prep.cohort.instructor_id,
        template_id=template.id,
        template_version_id=version.id,
        lang=lang,
        data=snapshot(prep, lang, custom, number, code),
        status="valid",
        comment=comment or None,
        issued_at=clock.now(),
        issued_by=p.id,
    )
    db.add(cert)
    await db.flush()
    name = str(prep.ctx.values["student.full_name"])
    diff: dict[str, Any] = {
        "number": [None, number],
        "template": [None, template.key],
        "cohort": [None, prep.cohort.code],
    }
    if comment:
        diff["comment"] = [None, comment]
    if non_graduate:
        diff["non_graduate"] = [None, True]
    await record(
        db, p.id, "certificate.reissue" if previous else "certificate.issue", "certificate",
        cert.id, diff, branch_id=cert.branch_id, label=f"{name} ({prep.cohort.code})",
    )  # fmt: skip
    return cert


def _out(cert: Certificate, name: str) -> dict[str, Any]:
    return {
        "id": cert.id,
        "number": cert.number,
        "verify_code": cert.verify_code,
        "student_name": name,
        "enrollment_id": cert.enrollment_id,
        "status": cert.status,
        "issued_at": cert.issued_at,
    }


async def _lock(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Enrollment]:
    """The enrollment rows `FOR UPDATE`, always in id order: two batches never wait in a circle."""
    rows = (
        (
            await db.execute(
                select(Enrollment)
                .where(Enrollment.id.in_(ids))
                .order_by(Enrollment.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    return {e.id: e for e in rows}


async def _already_issued(db: AsyncSession, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    found = (
        await db.execute(
            select(Certificate.enrollment_id).where(
                Certificate.enrollment_id.in_(ids), Certificate.status == "valid"
            )
        )
    ).scalars()
    return [e for e in found if e is not None]


@router.post("/cohorts/{cohort_id}/certificates/issue", status_code=201)
async def issue_batch(cohort_id: uuid.UUID, body: IssueBatch, p: Change, db: DB) -> dict[str, Any]:
    """One transaction for the whole batch: every id is ready or nothing is issued."""
    cohort, _ = await _cohort(db, p, cohort_id)
    _finished(cohort)
    template = await chosen_template(db, body.template_id)
    version = await published_version(db, template)
    layout = layout_of(version)
    lang = body.lang or template.lang
    custom = clean_custom(body.custom)
    ids = sorted(set(body.enrollment_ids))
    locked = await _lock(db, ids)
    if len(locked) != len(ids) or any(e.cohort_id != cohort.id for e in locked.values()):
        raise DomainError(NOT_FOUND)
    if issued := await _already_issued(db, ids):
        raise DomainError(CERT_ALREADY_ISSUED, enrollment_ids=sorted(issued))
    settings_row = await load_settings(db)
    cache = AssetCache(db)
    preps: list[Prepared] = []
    problems: list[dict[str, Any]] = []
    for eid in ids:
        prep = await prepare(db, eid, layout, lang, custom, cache, settings_row)
        name = str(prep.ctx.values["student.full_name"])
        fix = (
            Fix("not_graduate", FIX_TEXTS["not_graduate"])
            if prep.enrollment.status != GRADUATE
            else fix_of(layout, prep.ctx, prep.assets)
        )
        if fix:
            problems.append(_fix_item(eid, name, fix))
        preps.append(prep)
    if problems:
        raise DomainError(CERT_NOT_READY, items=problems)
    created = [
        _out(
            await _create(db, p, prep, template, version, lang, custom, None),
            str(prep.ctx.values["student.full_name"]),
        )
        for prep in preps
    ]
    return {"items": created, "count": len(created)}


@router.post("/enrollments/{enrollment_id}/certificate", status_code=201)
async def issue_one(enrollment_id: uuid.UUID, body: IssueOne, p: Change, db: DB) -> dict[str, Any]:
    """One certificate. A non-graduate gets one only when the superadmin allowed it in the
    settings, and then with a comment."""
    found = (
        await db.execute(
            select(Cohort, Course)
            .join(Enrollment, Enrollment.cohort_id == Cohort.id)
            .join(Course, Course.id == Cohort.course_id)
            .where(Enrollment.id == enrollment_id)
        )
    ).first()
    if found is None:
        raise DomainError(NOT_FOUND)
    cohort, course = found
    p.check_scope(cohort.branch_id)
    _finished(cohort)
    if body.template_id is not None:
        template = await chosen_template(db, body.template_id)
    else:
        template = await pick_template(db, course.id, cohort.instructor_id)
    version = await published_version(db, template)
    layout = layout_of(version)
    lang = body.lang or template.lang
    custom = clean_custom(body.custom)
    enrollment = (await _lock(db, [enrollment_id]))[enrollment_id]
    if await _already_issued(db, [enrollment_id]):
        raise DomainError(CERT_ALREADY_ISSUED, enrollment_ids=[enrollment_id])
    settings_row = await load_settings(db)
    non_graduate = enrollment.status != GRADUATE
    if non_graduate:
        if not settings_row.allow_non_graduate:
            raise DomainError(NOT_GRADUATE)
        if not allows(p.level("cert_templates"), "change"):
            raise DomainError(FORBIDDEN, section="cert_templates", level="change")
        if not body.comment:
            raise DomainError(CERT_COMMENT_REQUIRED).for_field("comment", "required")
    prep = await prepare(db, enrollment_id, layout, lang, custom, AssetCache(db), settings_row)
    name = str(prep.ctx.values["student.full_name"])
    if fix := fix_of(layout, prep.ctx, prep.assets):
        raise DomainError(CERT_NOT_READY, items=[_fix_item(enrollment_id, name, fix)])
    cert = await _create(
        db, p, prep, template, version, lang, custom, body.comment, non_graduate=non_graduate
    )
    return _out(cert, name)


# ---- reissue and revoke ----------------------------------------------------------------------


async def _locked_valid(
    db: AsyncSession, p: Principal, certificate_id: uuid.UUID
) -> tuple[Certificate, Enrollment | None]:
    """The certificate and its enrollment (none for a batch one), locked, the enrollment first."""
    cert = await db.get(Certificate, certificate_id)
    if cert is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(cert.branch_id)
    enrollment = None
    if cert.enrollment_id is not None:
        enrollment = (await _lock(db, [cert.enrollment_id]))[cert.enrollment_id]
    await db.refresh(cert, with_for_update=True)
    if cert.status != "valid":
        raise DomainError(CERT_NOT_VALID, status=cert.status)
    return cert, enrollment


@router.post("/certificates/{certificate_id}/reissue", status_code=201)
async def reissue(certificate_id: uuid.UUID, body: Reissue, p: Change, db: DB) -> dict[str, Any]:
    """A new certificate with fresh data and the same number; the old one becomes `replaced`."""
    old, _ = await _locked_valid(db, p, certificate_id)
    if old.cohort_id is None or old.enrollment_id is None:
        raise DomainError(CERT_BATCH_FIXED)  # revoke it and issue again from a new list
    _finished((await db.get(Cohort, old.cohort_id)) or _gone())
    template = await chosen_template(db, body.template_id or old.template_id)
    version = await published_version(db, template)
    layout = layout_of(version)
    custom = dict(old.data.get("custom") or {})
    prep = await prepare(
        db, old.enrollment_id, layout, old.lang, custom, AssetCache(db), await load_settings(db),
        number=old.number,
    )  # fmt: skip
    name = str(prep.ctx.values["student.full_name"])
    if fix := fix_of(layout, prep.ctx, prep.assets):
        raise DomainError(CERT_NOT_READY, items=[_fix_item(old.enrollment_id, name, fix)])
    old.status = "replaced"
    await db.flush()  # frees the one-valid slot of the enrollment
    new = await _create(
        db, p, prep, template, version, old.lang, custom, body.comment, previous=old
    )
    old.replaced_by_id = new.id
    await db.flush()
    return _out(new, name)


@router.post("/certificates/{certificate_id}/revoke")
async def revoke(certificate_id: uuid.UUID, body: Revoke, p: Change, db: DB) -> dict[str, Any]:
    cert, _ = await _locked_valid(db, p, certificate_id)
    cert.status, cert.revoke_reason = "revoked", body.reason
    cert.revoked_at, cert.revoked_by = clock.now(), p.id
    await db.flush()
    name = str(cert.data["values"].get("student.full_name", ""))
    cohort_code = (
        await db.scalar(select(Cohort.code).where(Cohort.id == cert.cohort_id))
        if cert.cohort_id
        else BULK_LABEL
    )
    await record(
        db, p.id, "certificate.revoke", "certificate", cert.id,
        {"number": [None, cert.number], "reason": [None, body.reason]},
        branch_id=cert.branch_id, label=f"{name} ({cohort_code})",
    )  # fmt: skip
    return _out(cert, name)


# ---- registry --------------------------------------------------------------------------------


def _select() -> Any:
    return (
        select(
            Certificate,
            Student.full_name.label("student_name"),
            Student.id.label("student_id"),
            Cohort.code.label("cohort_code"),
            Course.name.label("course_name"),
            Branch.name.label("branch_name"),
            AppUser.full_name.label("instructor_name"),
            Issuer.full_name.label("issued_by_name"),
            CertTemplate.name.label("template_name"),
        )
        .outerjoin(Enrollment, Enrollment.id == Certificate.enrollment_id)
        .outerjoin(
            Student, Student.id == func.coalesce(Certificate.student_id, Enrollment.student_id)
        )
        .outerjoin(Cohort, Cohort.id == Certificate.cohort_id)
        .outerjoin(Course, Course.id == Certificate.course_id)
        .join(Branch, Branch.id == Certificate.branch_id)
        .join(CertTemplate, CertTemplate.id == Certificate.template_id)
        .outerjoin(AppUser, AppUser.id == Certificate.instructor_id)
        .outerjoin(Issuer, Issuer.id == Certificate.issued_by)
    )


def _row(r: Any) -> dict[str, Any]:
    c: Certificate = r.Certificate
    return {
        "id": c.id,
        "number": c.number,
        "verify_code": c.verify_code,
        "status": c.status,
        "enrollment_id": c.enrollment_id,
        "student_id": r.student_id,
        "batch_id": c.batch_id,
        # the name as printed on the certificate
        "student_name": c.data["values"].get("student.full_name") or r.student_name,
        "cohort_id": c.cohort_id,
        "cohort_code": r.cohort_code,
        "course_id": c.course_id,
        "course_name": r.course_name or c.data["values"].get("course.name") or None,
        "branch_id": c.branch_id,
        "branch_name": r.branch_name,
        "instructor_id": c.instructor_id,
        "instructor_name": r.instructor_name,
        "template_id": c.template_id,
        "template_name": r.template_name,
        "lang": c.lang,
        "comment": c.comment,
        "revoke_reason": c.revoke_reason,
        "replaced_by_id": c.replaced_by_id,
        "issued_at": c.issued_at,
        "issued_by": c.issued_by,
        "issued_by_name": r.issued_by_name,
    }


STATUS_RU = {"valid": "Действует", "replaced": "Заменён", "revoked": "Отозван"}
REGISTRY_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Номер", lambda r: r["number"]),
    Col("Студент", lambda r: r["student_name"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Поток", lambda r: r["cohort_code"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Инструктор", lambda r: r["instructor_name"]),
    Col("Шаблон", lambda r: r["template_name"]),
    Col("Статус", lambda r: STATUS_RU[r["status"]]),
    Col("Выдан", lambda r: r["issued_at"], "datetime"),
    Col("Комментарий", lambda r: r["comment"]),
    Col("Причина отзыва", lambda r: r["revoke_reason"]),
]


@router.get("/certificates", response_model=None)
async def registry(
    p: View,
    db: DB,
    status: Literal["valid", "replaced", "revoked"] | None = None,
    course_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    instructor_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    template_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
    format: Annotated[Literal["xlsx"] | None, Query()] = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> Any:
    if branch_id:
        p.check_scope(branch_id)
    where: list[ColumnElement[bool]] = []
    if p.branch_id is not None:
        where.append(Certificate.branch_id == p.branch_id)
    if is_instructor(p):  # only the certificates of their own cohorts
        where.append(Cohort.instructor_id == p.id)
    for column, value in (
        (Certificate.status, status),
        (Certificate.course_id, course_id),
        (Certificate.cohort_id, cohort_id),
        (Certificate.instructor_id, instructor_id),
        (Certificate.branch_id, branch_id),
        (Certificate.template_id, template_id),
        (Certificate.batch_id, batch_id),
    ):
        if value is not None:
            where.append(column == value)
    day = func.date(func.timezone(clock.TZ.key, Certificate.issued_at))
    if date_from:
        where.append(day >= date_from)
    if date_to:
        where.append(day <= date_to)
    if q and q.strip():
        name_in_snapshot = Certificate.data["values"]["student.full_name"].as_string()
        where.append(
            or_(
                search_clause(q, (Student.full_name, name_in_snapshot)),
                Certificate.number.ilike(f"%{q.strip().replace('%', '').replace('_', '')}%"),
            )
        )
    order = (Certificate.issued_at.desc(), Certificate.number.desc(), Certificate.id)
    base = _select().where(and_(*where)) if where else _select()
    if format == "xlsx":
        found = (await db.execute(base.order_by(*order).limit(MAX_ROWS + 1))).all()
        export_rows = [_row(r) for r in found]
        check_cap(export_rows)
        return await xlsx_response(
            db, p, entity="certificate", slug="sertifikaty", title="Сертификаты",
            columns=REGISTRY_COLUMNS, rows=export_rows,
            filters={
                "status": status, "course_id": course_id, "cohort_id": cohort_id,
                "instructor_id": instructor_id, "branch_id": branch_id,
                "template_id": template_id, "batch_id": batch_id, "date_from": date_from,
                "date_to": date_to, "q": q,
            },
        )  # fmt: skip
    total = (
        await db.execute(
            _select().with_only_columns(func.count(Certificate.id)).where(and_(*where))
            if where
            else _select().with_only_columns(func.count(Certificate.id))
        )
    ).scalar_one()
    rows = (
        await db.execute(base.order_by(*order).limit(page_size).offset((page - 1) * page_size))
    ).all()
    return {
        "items": [_row(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _one(db: AsyncSession, p: Principal, certificate_id: uuid.UUID) -> Any:
    row = (await db.execute(_select().where(Certificate.id == certificate_id))).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(row.Certificate.branch_id)
    if is_instructor(p):
        owner = await db.scalar(
            select(Cohort.instructor_id).where(Cohort.id == row.Certificate.cohort_id)
        )
        if owner != p.id:
            raise DomainError(NOT_FOUND)
    return row


@router.get("/certificates/{certificate_id}")
async def get_certificate(certificate_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    row = await _one(db, p, certificate_id)
    cert: Certificate = row.Certificate
    previous = (
        await db.execute(select(Certificate.id).where(Certificate.replaced_by_id == cert.id))
    ).scalars()
    return {
        **_row(row),
        "values": cert.data["values"],
        "custom": cert.data.get("custom", {}),
        "revoked_at": cert.revoked_at,
        "revoked_by": cert.revoked_by,
        "replaces": list(previous),
    }


@router.get("/certificates/{certificate_id}/pdf")
async def certificate_pdf(certificate_id: uuid.UUID, p: View, db: DB) -> Response:
    """The PDF as issued: the stored template version and the stored values."""
    row = await _one(db, p, certificate_id)
    cert: Certificate = row.Certificate
    pdf = await render_certificate(db, cert)
    name = str(cert.data["values"].get("student.full_name", ""))
    await record(
        db, p.id, "certificate.pdf", "certificate", cert.id,
        {"number": [None, cert.number]}, branch_id=cert.branch_id,
        label=f"{name} ({row.cohort_code or BULK_LABEL})",
    )  # fmt: skip
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{file_name(cert.number, name)}"'},
    )
