"""Leads: list, create, edit, delete, convert into a student, CSV import, Excel export.

Rights: `leads` view / change, branch scope; the instructor role has no access. Names are cleaned
and flagged for review (#15) in `hygiene`; the counts and the funnel come from `app.metrics`.
A phone that is already a lead or a student is a warning, never a block: people come back.
"""

import json
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require_csrf_header
from app.cohorts import status as cohort_status
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, VALIDATION_FAILED, DomainError
from app.core.versioning import Version, check_version
from app.education.errors import COHORT_CLOSED, COHORT_FULL, STUDENT_BRANCH_MISMATCH
from app.education.scope import (
    branch_for_write,
    check_cohort_visible,
    is_instructor,
    student_filters,
)
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.leads import importer
from app.leads.errors import (
    CAMPAIGN_BRANCH_MISMATCH,
    IMPORT_TOO_LARGE,
    LEAD_CONVERTED,
    LEAD_USE_CONVERT,
)
from app.leads.hygiene import clean_name, phone_key, phone_parts, phone_plausible
from app.leads.query import lead_where
from app.leads.scope import LeadReader, LeadWriter
from app.metrics import cohort_enrolled
from app.metrics.sales import CALL_STATUSES, CONVERTED, LEAD_STATUSES
from app.models import Branch, Campaign, Cohort, Course, Enrollment, Lead, Student
from app.permissions import allows

router = APIRouter(
    prefix="/api/v1/leads", tags=["leads"], dependencies=[Depends(require_csrf_header)]
)

Source = Literal[
    "Facebook", "Instagram", "TikTok", "Telegram", "сайт", "рекомендация", "звонок", "другое"
]
CallStatus = Literal["не звонили", "не ответил", "позвонили", "перезвонить"]
OpenStatus = Literal["новый", "заинтересован", "нулевой урок", "отказ"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
RawName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
DUPLICATE_LIMIT = 5


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LeadCreate(Strict):
    full_name: RawName
    phone: Phone | None = None
    course_id: uuid.UUID | None = None
    source: Source = "другое"
    campaign_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    call_status: CallStatus = "не звонили"
    next_contact_at: datetime | None = None
    status: OpenStatus = "новый"
    refusal_reason: Text | None = None
    comment: Text | None = None


class LeadUpdate(Strict):
    """Only the fields present change. `status` «записан» comes from converting the lead."""

    full_name: RawName | None = None
    phone: Phone | None = None
    course_id: uuid.UUID | None = None
    source: Source | None = None
    campaign_id: uuid.UUID | None = None
    call_status: CallStatus | None = None
    next_contact_at: datetime | None = None
    status: Literal["новый", "заинтересован", "нулевой урок", "записан", "отказ"] | None = None
    refusal_reason: Text | None = None
    comment: Text | None = None
    needs_review: bool | None = None


class ConvertIn(Strict):
    cohort_id: uuid.UUID | None = None


# ---- output -----------------------------------------------------------------------------


def _out(lead: Lead, branch: str, course: str | None, campaign: str | None) -> dict[str, Any]:
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "raw_name": lead.raw_name,
        "phone": lead.phone,
        "phone_raw": lead.phone_raw,
        "course_id": lead.course_id,
        "course_name": course,
        "source": lead.source,
        "campaign_id": lead.campaign_id,
        "campaign_name": campaign,
        "branch_id": lead.branch_id,
        "branch_name": branch,
        "call_status": lead.call_status,
        "next_contact_at": lead.next_contact_at,
        "status": lead.status,
        "refusal_reason": lead.refusal_reason,
        "comment": lead.comment,
        "needs_review": lead.needs_review,
        "converted_student_id": lead.converted_student_id,
        "created_at": lead.created_at,
        "version": lead.version,
    }


def _snapshot(lead: Lead) -> dict[str, Any]:
    return {
        "full_name": lead.full_name,
        "phone": lead.phone,
        "course_id": lead.course_id,
        "source": lead.source,
        "campaign_id": lead.campaign_id,
        "call_status": lead.call_status,
        "next_contact_at": lead.next_contact_at,
        "status": lead.status,
        "refusal_reason": lead.refusal_reason,
        "comment": lead.comment,
        "needs_review": lead.needs_review,
    }


def _select(where: list[Any]) -> Any:
    return (
        select(Lead, Branch.name, Course.name, Campaign.name)
        .join(Branch, Branch.id == Lead.branch_id)
        .outerjoin(Course, Course.id == Lead.course_id)
        .outerjoin(Campaign, Campaign.id == Lead.campaign_id)
        .where(*where)
    )


def _order(callback: bool) -> list[Any]:
    if callback:
        return [Lead.next_contact_at.asc(), Lead.id]
    return [Lead.created_at.desc(), Lead.id]


async def _load(db: AsyncSession, p: Principal, lead_id: uuid.UUID) -> Lead:
    lead = (
        await db.execute(select(Lead).where(Lead.id == lead_id, *lead_where(p)))
    ).scalar_one_or_none()
    if lead is None:
        raise DomainError(NOT_FOUND)
    return lead


async def _detail(db: AsyncSession, p: Principal, lead: Lead) -> dict[str, Any]:
    row = (await db.execute(_select([Lead.id == lead.id]))).one()
    return _out(row[0], row[1], row[2], row[3])


# ---- duplicates -------------------------------------------------------------------------


async def duplicates(
    db: AsyncSession, p: Principal, phone: str | None, *, skip_lead: uuid.UUID | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Leads and students (in the user's scope) that have the same phone: a warning with links."""
    found: dict[str, list[dict[str, Any]]] = {"leads": [], "students": []}
    key = phone_key(phone)
    if key is None:
        return found
    lead_rows = await db.execute(
        select(Lead.id, Lead.full_name, Lead.status, Lead.created_at)
        .where(func.phone_key(Lead.phone) == key, *lead_where(p))
        .where(Lead.id != skip_lead if skip_lead else Lead.id.is_not(None))
        .order_by(Lead.created_at.desc())
        .limit(DUPLICATE_LIMIT)
    )
    found["leads"] = [
        {"id": i, "full_name": n, "status": s, "created_at": c} for i, n, s, c in lead_rows.all()
    ]
    if allows(p.level("students"), "view") and not is_instructor(p):
        student_rows = await db.execute(
            select(Student.id, Student.full_name)
            .where(func.phone_key(Student.phone) == key, *student_filters(p))
            .order_by(Student.created_at.desc())
            .limit(DUPLICATE_LIMIT)
        )
        found["students"] = [{"id": i, "full_name": n} for i, n in student_rows.all()]
    return found


def _with_warning(out: dict[str, Any], dup: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {**out, "duplicates": dup if dup["leads"] or dup["students"] else None}


async def _check_campaign(
    db: AsyncSession, p: Principal, campaign_id: uuid.UUID | None, branch_id: uuid.UUID
) -> None:
    if campaign_id is None:
        return
    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if campaign is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(campaign.branch_id)
    if campaign.branch_id != branch_id:
        raise DomainError(CAMPAIGN_BRANCH_MISMATCH)


async def _check_course(db: AsyncSession, course_id: uuid.UUID | None) -> None:
    if (
        course_id is not None
        and not (await db.execute(select(Course.id).where(Course.id == course_id))).first()
    ):
        raise DomainError(NOT_FOUND)


# ---- list, export, summary --------------------------------------------------------------

Filters = dict[str, Any]


def _filters(
    q: str | None,
    status: str | None,
    call_status: str | None,
    source: str | None,
    course_id: uuid.UUID | None,
    campaign_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    needs_review: bool | None,
    callback: bool,
    date_from: date | None,
    date_to: date | None,
) -> Filters:
    return {
        "q": q,
        "status": status,
        "call_status": call_status,
        "source": source,
        "course_id": course_id,
        "campaign_id": campaign_id,
        "branch_id": branch_id,
        "needs_review": needs_review,
        "callback": callback,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get("")
async def list_leads(
    p: LeadReader,
    db: DB,
    q: str | None = None,
    status: Annotated[str | None, Query(pattern="^(" + "|".join(LEAD_STATUSES) + ")$")] = None,
    call_status: Annotated[str | None, Query(pattern="^(" + "|".join(CALL_STATUSES) + ")$")] = None,
    source: str | None = None,
    course_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    callback: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    where = lead_where(
        p,
        **_filters(
            q, status, call_status, source, course_id, campaign_id, branch_id,
            needs_review, callback, date_from, date_to,
        ),
    )  # fmt: skip
    total = (await db.execute(select(func.count()).select_from(Lead).where(*where))).scalar_one()
    rows = (
        await db.execute(
            _select(where)
            .order_by(*_order(callback))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return {
        "items": [_out(*r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


LEAD_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("ФИО", lambda r: r["full_name"]),
    Col("Телефон", lambda r: r["phone"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Источник", lambda r: r["source"]),
    Col("Кампания", lambda r: r["campaign_name"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Статус", lambda r: r["status"]),
    Col("Статус звонка", lambda r: r["call_status"]),
    Col("Перезвонить", lambda r: r["next_contact_at"], "datetime"),
    Col("Причина отказа", lambda r: r["refusal_reason"]),
    Col("Нужна проверка", lambda r: r["needs_review"], "bool"),
    Col("Комментарий", lambda r: r["comment"]),
    Col("Создан", lambda r: r["created_at"], "date"),
]


@router.get("/export")
async def export_leads(
    p: LeadReader,
    db: DB,
    q: str | None = None,
    status: str | None = None,
    call_status: str | None = None,
    source: str | None = None,
    course_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    callback: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    f = _filters(
        q, status, call_status, source, course_id, campaign_id, branch_id,
        needs_review, callback, date_from, date_to,
    )  # fmt: skip
    rows = (
        await db.execute(
            _select(lead_where(p, **f)).order_by(*_order(callback)).limit(MAX_ROWS + 1)
        )
    ).all()
    check_cap(rows)
    return await xlsx_response(
        db,
        p,
        entity="lead",
        slug="lidy",
        title="Лиды",
        columns=LEAD_COLUMNS,
        rows=[_out(*r) for r in rows],
        filters=f,
    )


# ---- create, read, update, delete -------------------------------------------------------


def _apply_name(lead: Lead, raw: str) -> None:
    cleaned = clean_name(raw)
    lead.full_name, lead.raw_name, lead.needs_review = cleaned.name, raw, cleaned.needs_review


@router.post("", status_code=201)
async def create_lead(body: LeadCreate, p: LeadWriter, db: DB) -> dict[str, Any]:
    branch_id = branch_for_write(p, body.branch_id)
    await _check_course(db, body.course_id)
    await _check_campaign(db, p, body.campaign_id, branch_id)
    phone, phone_raw = phone_parts(body.phone)
    lead = Lead(
        phone=phone,
        phone_raw=phone_raw,
        course_id=body.course_id,
        source=body.source,
        campaign_id=body.campaign_id,
        branch_id=branch_id,
        call_status=body.call_status,
        next_contact_at=_callback_time(body.call_status, body.next_contact_at),
        status=body.status,
        refusal_reason=body.refusal_reason if body.status == "отказ" else None,
        comment=body.comment or None,
    )
    _apply_name(lead, body.full_name)
    lead.needs_review = lead.needs_review or not phone_plausible(phone_raw)
    db.add(lead)
    await db.flush()
    await record(
        db, p.id, "lead.create", "lead", lead.id, diff_of({}, _snapshot(lead)),
        branch_id=lead.branch_id,
    )  # fmt: skip
    dup = await duplicates(db, p, lead.phone, skip_lead=lead.id)
    return _with_warning(await _detail(db, p, lead), dup)


def _callback_time(call_status: str, when: datetime | None) -> datetime | None:
    """«перезвонить» without a time means «now»: it shows on today's callback list at once."""
    if call_status == "перезвонить" and when is None:
        return datetime.now(UTC)
    return when


@router.get("/{lead_id}")
async def get_lead(lead_id: uuid.UUID, p: LeadReader, db: DB) -> dict[str, Any]:
    lead = await _load(db, p, lead_id)
    dup = await duplicates(db, p, lead.phone, skip_lead=lead.id)
    return _with_warning(await _detail(db, p, lead), dup)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID, body: LeadUpdate, version: Version, p: LeadWriter, db: DB
) -> dict[str, Any]:
    lead = await _load(db, p, lead_id)

    async def current() -> dict[str, Any]:
        return await _detail(db, p, lead)

    await check_version(db, lead, version, "lead", current)
    before = _snapshot(lead)
    sent = body.model_fields_set
    if "status" in sent and body.status is not None and body.status != lead.status:
        if body.status == CONVERTED:
            raise DomainError(LEAD_USE_CONVERT)
        if lead.status == CONVERTED:
            raise DomainError(LEAD_CONVERTED)
    if "full_name" in sent and body.full_name and body.full_name != lead.raw_name:
        if body.full_name != lead.full_name:
            _apply_name(lead, body.full_name)
    if "needs_review" in sent and body.needs_review is not None:
        lead.needs_review = body.needs_review  # a person looked: the flag is theirs to set
    if "phone" in sent:
        lead.phone, lead.phone_raw = phone_parts(body.phone)
        if not phone_plausible(lead.phone_raw) and "needs_review" not in sent:
            lead.needs_review = True  # a number nobody can call goes to a person
    if "course_id" in sent:
        await _check_course(db, body.course_id)
        lead.course_id = body.course_id
    if "campaign_id" in sent:
        await _check_campaign(db, p, body.campaign_id, lead.branch_id)
        lead.campaign_id = body.campaign_id
    if "source" in sent and body.source:
        lead.source = body.source
    if "call_status" in sent and body.call_status:
        lead.call_status = body.call_status
        if "next_contact_at" not in sent:
            lead.next_contact_at = _callback_time(lead.call_status, lead.next_contact_at)
    if "next_contact_at" in sent:
        lead.next_contact_at = _callback_time(lead.call_status, body.next_contact_at)
    if "status" in sent and body.status:
        lead.status = body.status
    if "comment" in sent:
        lead.comment = body.comment or None
    if "refusal_reason" in sent:
        lead.refusal_reason = body.refusal_reason or None
    if lead.status != "отказ":
        lead.refusal_reason = None
    await db.flush()
    await record(
        db, p.id, "lead.update", "lead", lead.id, diff_of(before, _snapshot(lead)),
        branch_id=lead.branch_id,
    )  # fmt: skip
    dup = await duplicates(db, p, lead.phone, skip_lead=lead.id) if "phone" in sent else None
    out = await _detail(db, p, lead)
    return _with_warning(out, dup) if dup is not None else out


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: uuid.UUID, p: LeadWriter, db: DB) -> None:
    lead = await _load(db, p, lead_id)
    snapshot, branch_id = _snapshot(lead), lead.branch_id
    await db.delete(lead)
    await db.flush()
    await record(
        db, p.id, "lead.delete", "lead", lead_id, diff_of(snapshot, {}), branch_id=branch_id
    )


# ---- convert ----------------------------------------------------------------------------


async def _match_student(db: AsyncSession, lead: Lead) -> Student | None:
    """A student of the lead's branch with the same phone (the oldest one)."""
    key = phone_key(lead.phone)
    if key is None:
        return None
    return (
        (
            await db.execute(
                select(Student)
                .where(func.phone_key(Student.phone) == key, Student.branch_id == lead.branch_id)
                .order_by(Student.created_at, Student.id)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


@router.post("/{lead_id}/convert")
async def convert_lead(
    lead_id: uuid.UUID, body: ConvertIn, p: LeadWriter, db: DB
) -> dict[str, Any]:
    """Lead -> student in one action: link the student that has the lead's phone or create one in
    the lead's branch, optionally enroll into a cohort of that branch. Idempotent: converting
    again returns the same student (and enrolls if a cohort is named and it is not enrolled)."""
    lead = (
        await db.execute(select(Lead).where(Lead.id == lead_id, *lead_where(p)).with_for_update())
    ).scalar_one_or_none()
    if lead is None:
        raise DomainError(NOT_FOUND)
    # converting creates or links a student and shows who it is: a students write
    if not allows(p.level("students"), "change"):
        raise DomainError(FORBIDDEN, section="students", level="change")
    cohort: Cohort | None = None
    if body.cohort_id is not None:
        if not allows(p.level("cohorts"), "change"):
            raise DomainError(FORBIDDEN, section="cohorts", level="change")
        cohort = (
            await db.execute(select(Cohort).where(Cohort.id == body.cohort_id).with_for_update())
        ).scalar_one_or_none()
        if cohort is None:
            raise DomainError(NOT_FOUND)
        check_cohort_visible(p, cohort)
        if cohort.branch_id != lead.branch_id:
            raise DomainError(STUDENT_BRANCH_MISMATCH)
        if cohort.status in (cohort_status.CANCELLED, cohort_status.DONE):
            raise DomainError(COHORT_CLOSED)

    student: Student | None = None
    created = False
    if lead.converted_student_id is not None:
        student = (
            await db.execute(select(Student).where(Student.id == lead.converted_student_id))
        ).scalar_one_or_none()
    if student is None:
        student = await _match_student(db, lead)
    if student is None:
        student = Student(
            full_name=lead.full_name,
            phone=lead.phone,
            branch_id=lead.branch_id,
            source_lead_id=lead.id,
        )
        db.add(student)
        await db.flush()
        created = True
        await record(
            db, p.id, "student.create", "student", student.id,
            diff_of({}, {"full_name": student.full_name, "phone": student.phone}),
            branch_id=student.branch_id,
        )  # fmt: skip
    changed = lead.status != CONVERTED or lead.converted_student_id != student.id
    if changed:
        before_status = lead.status
        lead.status = CONVERTED
        lead.converted_student_id = student.id
        lead.refusal_reason = None
        await db.flush()
        await record(
            db, p.id, "lead.convert", "lead", lead.id,
            {
                "status": [before_status, CONVERTED],
                "student": [None, student.full_name],
                "student_new": [None, created],
            },
            branch_id=lead.branch_id,
        )  # fmt: skip
    enrollment = await _enroll(db, p, cohort, student) if cohort else None
    return {
        "lead": await _detail(db, p, lead),
        "student": {
            "id": student.id,
            "full_name": student.full_name,
            "phone": student.phone,
            "branch_id": student.branch_id,
            "created": created,
        },
        "enrollment": enrollment,
        "already": not changed and (enrollment is None or not enrollment["new"]),
    }


async def _enroll(
    db: AsyncSession, p: Principal, cohort: Cohort, student: Student
) -> dict[str, Any]:
    existing = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.cohort_id == cohort.id, Enrollment.student_id == student.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": existing.id, "cohort_id": cohort.id, "cohort_code": cohort.code, "new": False}
    if (await cohort_enrolled(db, [cohort.id]))[cohort.id] >= cohort.capacity:
        raise DomainError(COHORT_FULL)
    enrollment = Enrollment(cohort_id=cohort.id, student_id=student.id)
    db.add(enrollment)
    await db.flush()
    await record(
        db, p.id, "enrollment.create", "enrollment", enrollment.id,
        {
            "cohort": [None, cohort.code],
            "student": [None, student.full_name],
            "status": [None, enrollment.status],
        },
        branch_id=cohort.branch_id,
    )  # fmt: skip
    return {"id": enrollment.id, "cohort_id": cohort.id, "cohort_code": cohort.code, "new": True}


# ---- CSV import -------------------------------------------------------------------------


async def _read_body(request: Request) -> bytes:
    """The raw CSV, capped while it streams in (the limit holds even without Content-Length)."""
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > importer.MAX_BYTES:
        raise DomainError(IMPORT_TOO_LARGE, limit=importer.MAX_BYTES)
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > importer.MAX_BYTES:
            raise DomainError(IMPORT_TOO_LARGE, limit=importer.MAX_BYTES)
    return bytes(data)


def _mapping_of(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        raise DomainError(VALIDATION_FAILED) from None
    if not isinstance(data, dict):
        raise DomainError(VALIDATION_FAILED)
    return {str(k): (str(v) if v else None) for k, v in data.items()}


async def _prepare(
    db: AsyncSession,
    p: Principal,
    request: Request,
    mapping: str | None,
    source: str,
    course_id: uuid.UUID | None,
    campaign_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    *,
    strict: bool = True,
) -> tuple[list[str], dict[str, str | None], list[importer.Row], uuid.UUID]:
    """Parse and normalise the uploaded CSV and look up the duplicates. Reads only."""
    if source not in importer.SOURCES:
        raise DomainError(VALIDATION_FAILED)
    branch = branch_for_write(p, branch_id)
    await _check_course(db, course_id)
    await _check_campaign(db, p, campaign_id, branch)
    header, table = importer.parse_csv(await _read_body(request))
    given = _mapping_of(mapping)
    mapped = importer.check_mapping(
        header, given if given is not None else importer.detect_mapping(header), strict=strict
    )
    courses = {n.lower(): i for i, n in (await db.execute(select(Course.id, Course.name))).all()}
    rows = (
        importer.build_rows(
            header, table, mapped, default_source=source, default_course=course_id, courses=courses
        )
        if importer.complete(mapped)
        else []
    )
    await _mark_duplicates(db, p, rows)
    return header, mapped, rows, branch


async def _mark_duplicates(db: AsyncSession, p: Principal, rows: list[importer.Row]) -> None:
    keys = {k for r in rows if (k := phone_key(r.phone))}
    known: dict[str, list[dict[str, Any]]] = {}
    if keys:
        lead_rows = await db.execute(
            select(func.phone_key(Lead.phone), Lead.id, Lead.full_name)
            .where(func.phone_key(Lead.phone).in_(keys), *lead_where(p))
            .order_by(Lead.created_at.desc())
        )
        for key, i, name in lead_rows.all():
            known.setdefault(key, []).append({"kind": "lead", "id": i, "full_name": name})
        if allows(p.level("students"), "view") and not is_instructor(p):
            student_rows = await db.execute(
                select(func.phone_key(Student.phone), Student.id, Student.full_name).where(
                    func.phone_key(Student.phone).in_(keys), *student_filters(p)
                )
            )
            for key, i, name in student_rows.all():
                known.setdefault(key, []).append({"kind": "student", "id": i, "full_name": name})
    seen: dict[str, int] = {}
    for r in rows:
        key = phone_key(r.phone)
        if key is None:
            continue
        r.duplicates = known.get(key, [])[:3]
        if key in seen:
            r.duplicates = [*r.duplicates, {"kind": "file", "line": seen[key]}]
        else:
            seen[key] = r.line


def _row_out(r: importer.Row) -> dict[str, Any]:
    return {
        "line": r.line,
        "full_name": r.full_name,
        "raw_name": r.raw_name,
        "phone": r.phone,
        "phone_raw": r.phone_raw,
        "source": r.source,
        "course_id": r.course_id,
        "comment": r.comment,
        "needs_review": r.needs_review,
        "skip": r.skip,
        "duplicates": r.duplicates,
    }


PREVIEW_ROWS = 200


@router.post("/import/preview")
async def import_preview(
    request: Request,
    p: LeadWriter,
    db: DB,
    mapping: str | None = None,
    source: str = "Facebook",
    course_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Step 1+2 of the import: the body is the CSV itself (text/csv). Nothing is written."""
    header, mapped, rows, _ = await _prepare(
        db, p, request, mapping, source, course_id, campaign_id, branch_id, strict=False
    )
    usable = [r for r in rows if r.skip is None]
    return {
        "headers": header,
        "mapping": mapped,
        "rows": [_row_out(r) for r in rows[:PREVIEW_ROWS]],
        "truncated": len(rows) > PREVIEW_ROWS,
        "totals": {
            "rows": len(rows),
            "importable": len(usable),
            "skipped": len(rows) - len(usable),
            "needs_review": sum(r.needs_review for r in usable),
            "duplicates": sum(bool(r.duplicates) for r in usable),
        },
        "limits": {"bytes": importer.MAX_BYTES, "rows": importer.MAX_ROWS},
    }


@router.post("/import", status_code=201)
async def import_leads(
    request: Request,
    p: LeadWriter,
    db: DB,
    mapping: str | None = None,
    source: str = "Facebook",
    course_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Step 3: the same CSV and settings again; this call writes (one transaction)."""
    _, _, rows, branch = await _prepare(
        db, p, request, mapping, source, course_id, campaign_id, branch_id
    )
    usable = [r for r in rows if r.skip is None]
    for r in usable:
        db.add(
            Lead(
                full_name=r.full_name,
                raw_name=r.raw_name,
                phone=r.phone,
                phone_raw=r.phone_raw,
                course_id=r.course_id,
                source=r.source,
                campaign_id=campaign_id,
                branch_id=branch,
                comment=r.comment,
                needs_review=r.needs_review,
            )
        )
    await db.flush()
    review = sum(r.needs_review for r in usable)
    await record(
        db, p.id, "lead.import", "lead", None,
        {"created": [None, len(usable)], "needs_review": [None, review]},
        branch_id=branch, label=f"{len(usable)}",
    )  # fmt: skip
    return {
        "created": len(usable),
        "skipped": len(rows) - len(usable),
        "needs_review": review,
        "duplicates": sum(bool(r.duplicates) for r in usable),
    }
