"""Certificate PDFs and the template list (stage C1).

Rights: the PDF needs `graduates` view and the branch scope (like the graduates list);
templates and the preview need `cert_templates` view. A template's published version is what
renders; no editor yet.
"""

import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.auth.deps import Principal, require, require_csrf_header
from app.certificates.assets import load_assets
from app.certificates.errors import CERT_NO_TEMPLATE, CERT_NOT_ISSUED
from app.certificates.fields import SAMPLE_KINDS, enrollment_context, sample_context
from app.certificates.layout import Layout, parse_layout
from app.certificates.render import render_pdf
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.importer.parse import _CYR
from app.leads.scope import reader
from app.models import CertTemplate, CertTemplateRule, CertTemplateVersion

router = APIRouter(
    prefix="/api/v1", tags=["certificates"], dependencies=[Depends(require_csrf_header)]
)

GraduatesView = Annotated[Principal, reader("graduates")]
TemplatesView = Annotated[Principal, require("cert_templates", "view")]
DEFAULT_KEY = "general_ru"


async def latest_layout(db: AsyncSession, template: CertTemplate) -> Layout:
    layout = (
        await db.execute(
            select(CertTemplateVersion.layout)
            .where(CertTemplateVersion.template_id == template.id)
            .order_by(CertTemplateVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if layout is None:
        raise DomainError(CERT_NO_TEMPLATE)
    return parse_layout(layout)


async def pick_template(
    db: AsyncSession, course_id: uuid.UUID, instructor_id: uuid.UUID | None
) -> CertTemplate:
    """The template of the rule for (course, instructor), then for the course alone, then the
    default `general_ru`."""
    rules = (
        await db.execute(
            select(CertTemplateRule.instructor_id, CertTemplate)
            .join(CertTemplate, CertTemplate.id == CertTemplateRule.template_id)
            .where(CertTemplateRule.course_id == course_id, CertTemplate.status == "active")
        )
    ).all()
    by_instructor = {i: t for i, t in rules}
    if instructor_id is not None and instructor_id in by_instructor:
        return by_instructor[instructor_id]
    if None in by_instructor:
        return by_instructor[None]
    default = (
        await db.execute(select(CertTemplate).where(CertTemplate.key == DEFAULT_KEY))
    ).scalar_one_or_none()
    if default is None:
        raise DomainError(CERT_NO_TEMPLATE)
    return default


def file_name(number: str, student: str) -> str:
    """`CERT-2026-0001_karimov_ali.pdf`: the name transliterated to plain Latin."""
    latin = "".join(_CYR.get(ch, ch) for ch in student.lower().replace("ё", "е"))
    slug = re.sub(r"[^a-z0-9]+", "_", latin).strip("_") or "student"
    return f"{re.sub(r'[^A-Za-z0-9-]', '', number)}_{slug}.pdf"


@router.get("/graduates/{enrollment_id}/certificate/pdf")
async def certificate_pdf(
    enrollment_id: uuid.UUID, p: GraduatesView, db: DB, template_id: uuid.UUID | None = None
) -> Response:
    ctx, cohort, course, instructor, enrollment = await enrollment_context(db, enrollment_id)
    p.check_scope(cohort.branch_id)
    if not enrollment.certificate_no:
        raise DomainError(CERT_NOT_ISSUED)
    if template_id is not None:
        template = await db.get(CertTemplate, template_id)
        if template is None:
            raise DomainError(NOT_FOUND)
    else:
        template = await pick_template(db, course.id, instructor.id if instructor else None)
    layout = await latest_layout(db, template)
    assets = await load_assets(db, layout.asset_refs())
    pdf = await render_pdf(layout, ctx, assets)
    await record(
        db,
        p.id,
        "enrollment.certificate_pdf",
        "enrollment",
        enrollment.id,
        {"certificate_no": [None, enrollment.certificate_no], "template": [None, template.key]},
        branch_id=cohort.branch_id,
    )
    name = file_name(enrollment.certificate_no, str(ctx.values["student.full_name"]))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/cert-templates")
async def list_templates(p: TemplatesView, db: DB) -> dict[str, Any]:
    latest = (
        select(
            CertTemplateVersion.template_id,
            func.max(CertTemplateVersion.version_no).label("n"),
            func.max(CertTemplateVersion.published_at).label("at"),
        )
        .group_by(CertTemplateVersion.template_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(CertTemplate, latest.c.n, latest.c.at)
            .outerjoin(latest, latest.c.template_id == CertTemplate.id)
            .order_by(CertTemplate.name)
        )
    ).all()
    return {
        "items": [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "status": t.status,
                "lang": t.lang,
                "version_no": n,
                "published_at": at,
            }
            for t, n, at in rows
        ]
    }


@router.post("/cert-templates/{template_id}/preview")
async def preview(
    template_id: uuid.UUID,
    p: TemplatesView,
    db: DB,
    sample: Annotated[str, Query(pattern="^(short|long|female)$")] = "short",
) -> Response:
    """The latest version with sample data. Nothing is written: no audit entry, no registry."""
    assert sample in SAMPLE_KINDS
    template = await db.get(CertTemplate, template_id)
    if template is None:
        raise DomainError(NOT_FOUND)
    layout = await latest_layout(db, template)
    assets = await load_assets(db, layout.asset_refs())
    pdf = await render_pdf(layout, sample_context(sample), assets)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{template.key}_{sample}.pdf"'},
    )
