"""Certificate PDFs and the template list (stage C1).

Rights: the PDF needs `graduates` view and the branch scope (like the graduates list);
templates and the preview need `cert_templates` view. A template's published version is what
renders; the template editor API is in `editor.py`.
"""

import re
import uuid
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import anyio
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.certificates.assets import load_assets, store_asset
from app.certificates.errors import (
    CERT_ASSET_INVALID,
    CERT_DIRECTOR_OVERFLOW,
    CERT_NO_TEMPLATE,
    CERT_NOT_ISSUED,
    CERT_TEXT_OVERFLOW,
)
from app.certificates.fields import (
    SAMPLE_KINDS,
    apply_settings,
    director_for,
    enrollment_context,
    image_refs,
    load_settings,
    sample_context,
)
from app.certificates.layout import FieldRun, Layout, TextLayer, parse_layout
from app.certificates.render import fit_size, render_pdf, resolve_text
from app.certificates.signature import INKS, MAX_INPUT_BYTES
from app.certificates.signature import clean as clean_image
from app.certificates.stored import render_certificate
from app.core import clock
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.importer.parse import _CYR
from app.leads.scope import reader
from app.models import (
    AppUser,
    CertAsset,
    Certificate,
    CertSettings,
    CertTemplate,
    CertTemplateRule,
    CertTemplateVersion,
    Cohort,
    Course,
    Enrollment,
)

router = APIRouter(
    prefix="/api/v1", tags=["certificates"], dependencies=[Depends(require_csrf_header)]
)

GraduatesView = Annotated[Principal, reader("graduates")]
TemplatesView = Annotated[Principal, require("cert_templates", "view")]
TemplatesChange = Annotated[Principal, require("cert_templates", "change")]
DEFAULT_KEY = "general_ru"


async def latest_version(db: AsyncSession, template: CertTemplate) -> CertTemplateVersion:
    version = (
        await db.execute(
            select(CertTemplateVersion)
            .where(CertTemplateVersion.template_id == template.id)
            .order_by(CertTemplateVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version is None:
        raise DomainError(CERT_NO_TEMPLATE)
    return version


async def latest_layout(db: AsyncSession, template: CertTemplate) -> Layout:
    return parse_layout((await latest_version(db, template)).layout)


async def pin_default_version(
    db: AsyncSession, enrollment: Enrollment, course_id: uuid.UUID, instructor_id: uuid.UUID | None
) -> None:
    """At issue: the certificate is drawn from the version the rules choose now, for good.
    Without any published template nothing is pinned (the first PDF pins it)."""
    try:
        template = await pick_template(db, course_id, instructor_id)
        enrollment.certificate_version_id = (await latest_version(db, template)).id
    except DomainError:
        return
    await db.flush()


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


@router.get("/graduates/{enrollment_id}/certificate/templates")
async def certificate_templates(
    enrollment_id: uuid.UUID, p: GraduatesView, db: DB
) -> dict[str, Any]:
    """Templates a graduate's PDF can be rendered with: active ones that have a published
    version. `default_template_id` is the one the PDF uses when no template is chosen."""
    row = (
        await db.execute(
            select(Cohort, Course)
            .join(Enrollment, Enrollment.cohort_id == Cohort.id)
            .join(Course, Course.id == Cohort.course_id)
            .where(Enrollment.id == enrollment_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    cohort, course = row
    p.check_scope(cohort.branch_id)
    templates = (
        (
            await db.execute(
                select(CertTemplate)
                .where(
                    CertTemplate.status == "active",
                    select(CertTemplateVersion.id)
                    .where(CertTemplateVersion.template_id == CertTemplate.id)
                    .exists(),
                )
                .order_by(CertTemplate.lang, CertTemplate.name)
            )
        )
        .scalars()
        .all()
    )
    try:
        default: uuid.UUID | None = (await pick_template(db, course.id, cohort.instructor_id)).id
    except DomainError:
        default = None
    if default not in {t.id for t in templates}:
        default = templates[0].id if templates else None
    return {
        "default_template_id": default,
        "templates": [{"id": t.id, "name": t.name, "lang": t.lang} for t in templates],
    }


@router.get("/graduates/{enrollment_id}/certificate/pdf")
async def certificate_pdf(
    enrollment_id: uuid.UUID, p: GraduatesView, db: DB, template_id: uuid.UUID | None = None
) -> Response:
    ctx, cohort, course, instructor, enrollment = await enrollment_context(db, enrollment_id)
    p.check_scope(cohort.branch_id)
    if not enrollment.certificate_no:
        raise DomainError(CERT_NOT_ISSUED)
    issued = (
        await db.execute(
            select(Certificate).where(
                Certificate.enrollment_id == enrollment_id, Certificate.status == "valid"
            )
        )
    ).scalar_one_or_none()
    if issued is not None:  # an issued certificate renders as it was issued
        pdf = await render_certificate(db, issued)
        name = file_name(issued.number, str(issued.data["values"].get("student.full_name", "")))
        await record(
            db,
            p.id,
            "enrollment.certificate_pdf",
            "enrollment",
            enrollment.id,
            {"certificate_no": [None, issued.number], "template": [None, "issued"]},
            branch_id=cohort.branch_id,
        )
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    pinned = (
        await db.get(CertTemplateVersion, enrollment.certificate_version_id)
        if enrollment.certificate_version_id
        else None
    )
    if template_id is not None:
        template = await db.get(CertTemplate, template_id)
        if template is None:
            raise DomainError(NOT_FOUND)
    elif pinned is not None:
        template = await db.get(CertTemplate, pinned.template_id)
        assert template is not None
    else:
        template = await pick_template(db, course.id, instructor.id if instructor else None)
    # a certificate already drawn from this template keeps its version; another template (or the
    # first PDF) takes the newest published one and is remembered
    if pinned is not None and pinned.template_id == template.id:
        version = pinned
    else:
        version = await latest_version(db, template)
        enrollment.certificate_version_id = version.id
    apply_settings(ctx, await load_settings(db), template.lang)
    layout = parse_layout(version.layout)
    assets = await load_assets(db, [*layout.asset_refs(), *image_refs(ctx)])
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
    ctx = apply_settings(sample_context(sample), await load_settings(db), template.lang)
    assets = await load_assets(db, [*layout.asset_refs(), *image_refs(ctx)])
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
    director_name_en: Text120 | None = None
    director_title_en: Text120 | None = None
    director_name_tg: Text120 | None = None
    director_title_tg: Text120 | None = None
    # superadmin only; "" or null clears the address
    verify_base_url: str | None = None
    allow_non_graduate: bool | None = None

    @field_validator("verify_base_url")
    @classmethod
    def _origin(cls, value: str | None) -> str | None:
        """An https origin: no path, query, fragment or credentials (a trailing slash is fine)."""
        value = (value or "").strip()
        if not value:
            return None
        try:
            url = urlsplit(value)
            port = url.port
        except ValueError:
            raise ValueError("not a URL") from None
        ok = (
            url.scheme == "https"
            and url.hostname
            and url.username is None
            and url.password is None
            and url.path in ("", "/")
            and not url.query
            and not url.fragment
            and "?" not in value
            and "#" not in value
        )
        if not ok or len(value) > 200:
            raise ValueError("an https address without a path is needed")
        host = url.hostname or ""
        return f"https://{host}" + (f":{port}" if port else "")


DIRECTOR_KEYS = (
    "director_name",
    "director_title",
    "director_name_en",
    "director_title_en",
    "director_name_tg",
    "director_title_tg",
)
SUPERADMIN_ONLY = ("verify_base_url", "allow_non_graduate")


async def check_director_fits(db: AsyncSession, row: CertSettings, changes: dict[str, Any]) -> None:
    """The new director name or title must fit every active template; 422 names the ones that
    do not, instead of a failure at PDF time."""
    merged = CertSettings(**{k: changes.get(k, getattr(row, k)) for k in DIRECTOR_KEYS})
    templates = (
        (
            await db.execute(
                select(CertTemplate)
                .where(CertTemplate.status == "active")
                .order_by(CertTemplate.name)
            )
        )
        .scalars()
        .all()
    )
    bad: list[str] = []
    for template in templates:
        try:
            layout = await latest_layout(db, template)
        except DomainError:
            continue  # nothing published: nothing renders
        ctx = sample_context("short")
        ctx.values["company.director_name"], ctx.values["company.director_title"] = director_for(
            merged, template.lang
        )
        for layer in layout.layers:
            if not isinstance(layer, TextLayer) or not any(
                isinstance(r, FieldRun) and r.field.startswith("company.director")
                for r in layer.content
            ):
                continue
            try:
                fit_size(resolve_text(layer, ctx), layer)
            except DomainError as exc:
                if exc.error is not CERT_TEXT_OVERFLOW:
                    raise
                bad.append(template.name)
                break
    if bad:
        raise DomainError(CERT_DIRECTOR_OVERFLOW, templates=bad)


async def _settings_out(db: AsyncSession, row: CertSettings) -> dict[str, Any]:
    by = (
        await db.execute(select(AppUser.full_name).where(AppUser.id == row.updated_by))
    ).scalar_one_or_none()
    return {
        "director_name": row.director_name,
        "director_title": row.director_title,
        "director_name_en": row.director_name_en,
        "director_title_en": row.director_title_en,
        "director_name_tg": row.director_name_tg,
        "director_title_tg": row.director_title_tg,
        "signature_asset_id": row.director_signature_asset_id,
        "seal_asset_id": row.seal_asset_id,
        "verify_base_url": row.verify_base_url,
        "allow_non_graduate": row.allow_non_graduate,
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
    changes = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k == "verify_base_url"
    }
    if any(k in changes for k in SUPERADMIN_ONLY) and not p.is_superadmin:
        raise DomainError(FORBIDDEN, section="cert_settings", level="superadmin")

    async def current() -> dict[str, Any]:
        return await _settings_out(db, row)

    await check_version(db, row, version, "cert_settings", current, changes=changes)
    if any(k in changes for k in DIRECTOR_KEYS):
        await check_director_fits(db, row, changes)
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


async def read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise DomainError(CERT_ASSET_INVALID, reason="too_large")
    return data


async def cleaned_upload(file: UploadFile, ink: str) -> bytes:
    data = await read_upload(file)
    return await anyio.to_thread.run_sync(clean_image, data, ink)


async def _store_image(
    kind: str, file: UploadFile, ink: str, p: Principal, db: AsyncSession
) -> dict[str, Any]:
    png = await cleaned_upload(file, ink)
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
    return Response(await cleaned_upload(file, ink), media_type="image/png")


@router.post("/cert-settings/seal/preview")
async def preview_seal(
    p: TemplatesChange, file: Annotated[UploadFile, File()], ink: InkQuery = "original"
) -> Response:
    return Response(await cleaned_upload(file, ink), media_type="image/png")


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
