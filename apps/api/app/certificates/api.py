"""Certificate PDFs and the template list (stage C1).

Rights: the PDF needs `graduates` view and the branch scope (like the graduates list);
templates and the preview need `cert_templates` view. A template's published version is what
renders; no editor yet.
"""

import re
import uuid
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.certificates.assets import load_assets, store_asset
from app.certificates.errors import CERT_ASSET_INVALID, CERT_NO_TEMPLATE, CERT_NOT_ISSUED
from app.certificates.fields import (
    SAMPLE_KINDS,
    apply_settings,
    enrollment_context,
    load_settings,
    sample_context,
)
from app.certificates.layout import Layout, parse_layout
from app.certificates.render import render_pdf
from app.certificates.signature import INKS, MAX_INPUT_BYTES
from app.certificates.signature import clean as clean_image
from app.core import clock
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.importer.parse import _CYR
from app.leads.scope import reader
from app.models import (
    AppUser,
    CertAsset,
    CertSettings,
    CertTemplate,
    CertTemplateRule,
    CertTemplateVersion,
)

router = APIRouter(
    prefix="/api/v1", tags=["certificates"], dependencies=[Depends(require_csrf_header)]
)

GraduatesView = Annotated[Principal, reader("graduates")]
TemplatesView = Annotated[Principal, require("cert_templates", "view")]
TemplatesChange = Annotated[Principal, require("cert_templates", "change")]
DEFAULT_KEY = "general_ru"


def _director_refs(ctx: Any) -> list[str]:
    return [r for r in (ctx.signature_ref, ctx.seal_ref) if r]


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
    assets = await load_assets(db, [*layout.asset_refs(), *_director_refs(ctx)])
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
    ctx = apply_settings(sample_context(sample), await load_settings(db))
    assets = await load_assets(db, [*layout.asset_refs(), *_director_refs(ctx)])
    pdf = await render_pdf(layout, ctx, assets)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{template.key}_{sample}.pdf"'},
    )


# ---- settings: the company director ---------------------------------------------------------

Text120 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Title120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
IMAGES = {"signature": "director_signature_asset_id", "seal": "seal_asset_id"}
IMAGE_SENTENCE = {"signature": "подпись директора", "seal": "печать"}


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    director_name: Text120 | None = None
    director_title: Title120 | None = None


async def _settings_out(db: AsyncSession, row: CertSettings) -> dict[str, Any]:
    by = (
        await db.execute(select(AppUser.full_name).where(AppUser.id == row.updated_by))
    ).scalar_one_or_none()
    return {
        "director_name": row.director_name,
        "director_title": row.director_title,
        "signature_asset_id": row.director_signature_asset_id,
        "seal_asset_id": row.seal_asset_id,
        "version": row.version,
        "updated_at": row.updated_at,
        "updated_by": by,
    }


@router.get("/cert-settings")
async def get_settings(p: TemplatesView, db: DB) -> dict[str, Any]:
    return await _settings_out(db, await load_settings(db))


@router.patch("/cert-settings")
async def update_settings(
    body: SettingsUpdate, p: TemplatesChange, version: Version, db: DB
) -> dict[str, Any]:
    row = await load_settings(db)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)

    async def current() -> dict[str, Any]:
        return await _settings_out(db, row)

    await check_version(db, row, version, "cert_settings", current, changes=changes)
    before = {k: getattr(row, k) for k in changes}
    for key, value in changes.items():
        setattr(row, key, value)
    diff = diff_of(before, changes)
    if diff:
        row.updated_by, row.updated_at = p.id, clock.now()
        await db.flush()
        await record(
            db, p.id, "cert_settings.update", "cert_settings", str(row.id), diff,
            label="настройки сертификатов",
        )  # fmt: skip
    return await _settings_out(db, row)


async def _read_image(file: UploadFile) -> bytes:
    data = await file.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise DomainError(CERT_ASSET_INVALID, reason="too_large")
    return data


async def _cleaned(file: UploadFile, ink: str) -> bytes:
    data = await _read_image(file)
    return await anyio.to_thread.run_sync(clean_image, data, ink)


async def _store_image(
    kind: str, file: UploadFile, ink: str, p: Principal, db: AsyncSession
) -> dict[str, Any]:
    png = await _cleaned(file, ink)
    asset, _ = await store_asset(db, png, kind, p.id)
    row = await load_settings(db)
    column = IMAGES[kind]
    old = getattr(row, column)
    setattr(row, column, asset.id)
    row.updated_by, row.updated_at = p.id, clock.now()
    await db.flush()
    await record(
        db, p.id, f"cert_settings.{kind}_upload", "cert_settings", str(row.id),
        {kind: [old, asset.id]}, label="настройки сертификатов",
    )  # fmt: skip
    return await _settings_out(db, row)


async def _delete_image(kind: str, p: Principal, db: AsyncSession) -> dict[str, Any]:
    row = await load_settings(db)
    column = IMAGES[kind]
    old = getattr(row, column)
    if old is not None:
        setattr(row, column, None)
        row.updated_by, row.updated_at = p.id, clock.now()
        await db.flush()
        await record(
            db, p.id, f"cert_settings.{kind}_delete", "cert_settings", str(row.id),
            {kind: [old, None]}, label="настройки сертификатов",
        )  # fmt: skip
    return await _settings_out(db, row)


InkQuery = Annotated[str, Query(pattern="^(" + "|".join(INKS) + ")$")]


@router.post("/cert-settings/signature")
async def upload_signature(
    p: TemplatesChange, db: DB, file: Annotated[UploadFile, File()], ink: InkQuery = "original"
) -> dict[str, Any]:
    return await _store_image("signature", file, ink, p, db)


@router.post("/cert-settings/seal")
async def upload_seal(
    p: TemplatesChange, db: DB, file: Annotated[UploadFile, File()], ink: InkQuery = "original"
) -> dict[str, Any]:
    return await _store_image("seal", file, ink, p, db)


@router.post("/cert-settings/signature/preview")
async def preview_signature(
    p: TemplatesChange, file: Annotated[UploadFile, File()], ink: InkQuery = "original"
) -> Response:
    """The cleaned image, nothing saved."""
    return Response(await _cleaned(file, ink), media_type="image/png")


@router.post("/cert-settings/seal/preview")
async def preview_seal(
    p: TemplatesChange, file: Annotated[UploadFile, File()], ink: InkQuery = "original"
) -> Response:
    return Response(await _cleaned(file, ink), media_type="image/png")


@router.delete("/cert-settings/signature")
async def delete_signature(p: TemplatesChange, db: DB) -> dict[str, Any]:
    return await _delete_image("signature", p, db)


@router.delete("/cert-settings/seal")
async def delete_seal(p: TemplatesChange, db: DB) -> dict[str, Any]:
    return await _delete_image("seal", p, db)


@router.get("/cert-settings/{kind}")
async def get_image(kind: Literal["signature", "seal"], p: TemplatesView, db: DB) -> Response:
    """The stored signature or seal (PNG), for the settings screen."""
    asset_id = getattr(await load_settings(db), IMAGES[kind])
    asset = await db.get(CertAsset, asset_id) if asset_id else None
    if asset is None:
        raise DomainError(NOT_FOUND)
    return Response(
        asset.data, media_type=asset.mime, headers={"Cache-Control": "private, no-cache"}
    )
