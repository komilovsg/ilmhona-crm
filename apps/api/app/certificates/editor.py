"""The template editor API (stage C4): list, create, edit the draft, publish, restore, preview an
unsaved layout, images, the field catalog, bundled fonts and the course -> template rules.

Rights: section `cert_templates`, `view` for reads, `change` for writes (and for the draft
preview, which renders from a body). A draft is validated like a published layout; image
references in a layout are `cert_asset` ids and must exist.
"""

import re
import uuid
from datetime import date
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.certificates.assets import MAX_BYTES, inspect, load_assets, store_asset
from app.certificates.errors import (
    CERT_ASSET_INVALID,
    CERT_ASSET_MISSING,
    CERT_NOTHING_TO_PUBLISH,
    CERT_RULE_DUPLICATE,
    CERT_RULE_INVALID,
    CERT_TEMPLATE_NAME_TAKEN,
)
from app.certificates.fields import (
    DATE_FORMATS,
    FIELDS,
    SAMPLE_KINDS,
    apply_settings,
    director_for,
    format_date,
    load_settings,
    sample_context,
)
from app.certificates.fonts import DIR as FONT_DIR
from app.certificates.fonts import FAMILIES, font_files
from app.certificates.layout import Layout, parse_layout
from app.certificates.render import render_pdf
from app.core import clock
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version, lock
from app.importer.parse import _CYR
from app.models import (
    AppUser,
    CertAsset,
    CertTemplate,
    CertTemplateRule,
    CertTemplateVersion,
    Course,
)

router = APIRouter(
    prefix="/api/v1", tags=["certificate editor"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("cert_templates", "view")]
Change = Annotated[Principal, require("cert_templates", "change")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Lang = Literal["ru", "en", "tg"]
BLANK: dict[str, Any] = {
    "schema": 1,
    "page": {"width_mm": 297, "height_mm": 210},
    "background": None,
    "layers": [],
}
MAX_SIDE_PX = 8000
SERVED_KINDS = ("background", "image", "seal", "signature")
GROUPS = {
    "student": "Студент",
    "course": "Курс и поток",
    "cohort": "Курс и поток",
    "branch": "Курс и поток",
    "instructor": "Инструктор",
    "certificate": "Сертификат",
    "grade": "Сертификат",
    "company": "Директор",
}
DATE_KEYS = {k for k in FIELDS if k.endswith("_date")}


# ---- helpers ---------------------------------------------------------------------------------


def slug(name: str) -> str:
    latin = "".join(_CYR.get(ch, ch) for ch in name.lower().replace("ё", "е"))
    return re.sub(r"[^a-z0-9]+", "-", latin).strip("-")[:50].strip("-") or "template"


async def free_key(db: AsyncSession, name: str) -> str:
    base = slug(name)
    taken = set(
        (await db.execute(select(CertTemplate.key).where(CertTemplate.key.like(f"{base}%"))))
        .scalars()
        .all()
    )
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}-{n}"
    return key


async def get_template(db: AsyncSession, template_id: uuid.UUID) -> CertTemplate:
    template = await db.get(CertTemplate, template_id)
    if template is None:
        raise DomainError(NOT_FOUND)
    return template


async def name_free(db: AsyncSession, name: str, except_id: uuid.UUID | None = None) -> None:
    query = select(CertTemplate.id).where(func.lower(CertTemplate.name) == name.lower())
    if except_id is not None:
        query = query.where(CertTemplate.id != except_id)
    if (await db.execute(query)).first() is not None:
        raise DomainError(CERT_TEMPLATE_NAME_TAKEN)


async def check_layout(db: AsyncSession, data: Any) -> Layout:
    """The layout schema and the field catalog, then every image reference must be a stored
    asset (`cert_asset_missing`)."""
    layout = parse_layout(data)
    for ref in layout.asset_refs():
        try:
            asset_id = uuid.UUID(ref)
        except ValueError:
            raise DomainError(CERT_ASSET_MISSING, asset=ref) from None
        if await db.get(CertAsset, asset_id) is None:
            raise DomainError(CERT_ASSET_MISSING, asset=ref)
    return layout


async def latest(db: AsyncSession, template_id: uuid.UUID) -> CertTemplateVersion | None:
    return (
        await db.execute(
            select(CertTemplateVersion)
            .where(CertTemplateVersion.template_id == template_id)
            .order_by(CertTemplateVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def detail(db: AsyncSession, t: CertTemplate) -> dict[str, Any]:
    versions = (
        await db.execute(
            select(
                CertTemplateVersion.version_no,
                CertTemplateVersion.published_at,
                AppUser.full_name,
                CertTemplateVersion.layout,
            )
            .outerjoin(AppUser, AppUser.id == CertTemplateVersion.published_by)
            .where(CertTemplateVersion.template_id == t.id)
            .order_by(CertTemplateVersion.version_no.desc())
        )
    ).all()
    rules = (
        await db.execute(
            select(
                CertTemplateRule.course_id,
                Course.name,
                CertTemplateRule.instructor_id,
                AppUser.full_name,
            )
            .join(Course, Course.id == CertTemplateRule.course_id)
            .outerjoin(AppUser, AppUser.id == CertTemplateRule.instructor_id)
            .where(CertTemplateRule.template_id == t.id)
            .order_by(Course.name, AppUser.full_name)
        )
    ).all()
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "status": t.status,
        "lang": t.lang,
        "version": t.version,
        "updated_at": t.updated_at,
        "draft": t.draft,
        "latest_version_no": versions[0][0] if versions else None,
        "has_unpublished_changes": not versions or versions[0][3] != t.draft,
        "versions": [
            {"version_no": n, "published_at": at, "published_by_name": by}
            for n, at, by, _ in versions
        ],
        "rules": [
            {
                "course_id": c,
                "course_name": cn,
                "instructor_id": i,
                "instructor_name": inn,
            }
            for c, cn, i, inn in rules
        ],
    }


# ---- templates -------------------------------------------------------------------------------


@router.get("/cert-templates")
async def list_templates(p: View, db: DB) -> dict[str, Any]:
    newest = (
        select(
            CertTemplateVersion.template_id,
            func.max(CertTemplateVersion.version_no).label("n"),
        )
        .group_by(CertTemplateVersion.template_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(CertTemplate, newest.c.n, CertTemplateVersion.layout)
            .outerjoin(newest, newest.c.template_id == CertTemplate.id)
            .outerjoin(
                CertTemplateVersion,
                (CertTemplateVersion.template_id == newest.c.template_id)
                & (CertTemplateVersion.version_no == newest.c.n),
            )
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
                "version": t.version,
                "latest_version_no": n,
                "updated_at": t.updated_at,
                "has_unpublished_changes": n is None or layout != t.draft,
            }
            for t, n, layout in rows
        ]
    }


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    lang: Lang | None = None
    from_template_id: uuid.UUID | None = None


@router.post("/cert-templates", status_code=201)
async def create_template(body: TemplateCreate, p: Change, db: DB) -> dict[str, Any]:
    await name_free(db, body.name)
    draft: dict[str, Any] = BLANK
    lang: str = body.lang or "ru"
    if body.from_template_id is not None:
        source = await get_template(db, body.from_template_id)
        draft = source.draft
        lang = body.lang or source.lang
    template = CertTemplate(
        key=await free_key(db, body.name), name=body.name, lang=lang, draft=draft,
        updated_by=p.id, updated_at=clock.now(),
    )  # fmt: skip
    db.add(template)
    await db.flush()
    await record(
        db, p.id, "cert_template.create", "cert_template", template.id,
        {"name": [None, template.name]},
        label=template.name,
    )  # fmt: skip
    return await detail(db, template)


@router.get("/cert-templates/{template_id}")
async def get_one(template_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    return await detail(db, await get_template(db, template_id))


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    lang: Lang | None = None
    status: Literal["active", "archived"] | None = None
    draft: dict[str, Any] | None = None


@router.patch("/cert-templates/{template_id}")
async def update_template(
    template_id: uuid.UUID, body: TemplateUpdate, p: Change, version: Version, db: DB
) -> dict[str, Any]:
    template = await get_template(db, template_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "draft" in changes:
        changes["draft"] = (await check_layout(db, changes["draft"])).dump()
    if "name" in changes and changes["name"] != template.name:
        await name_free(db, changes["name"], template.id)

    async def current() -> dict[str, Any]:
        return await detail(db, template)

    await check_version(db, template, version, "cert_template", current, changes=changes)
    scalars = {k: v for k, v in changes.items() if k != "draft"}
    diff = diff_of({k: getattr(template, k) for k in scalars}, scalars)
    draft_changed = "draft" in changes and changes["draft"] != template.draft
    if diff or draft_changed:
        for key, value in changes.items():
            setattr(template, key, value)
        template.updated_by, template.updated_at = p.id, clock.now()
        await db.flush()
        if diff:
            await record(
                db, p.id, "cert_template.update", "cert_template", template.id, diff,
                label=template.name,
            )  # fmt: skip
        if draft_changed:
            await record(
                db, p.id, "cert_template.draft_update", "cert_template", template.id,
                label=template.name,
            )  # fmt: skip
    return await detail(db, template)


@router.post("/cert-templates/{template_id}/publish")
async def publish(template_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    template = await get_template(db, template_id)
    await lock(db, template)
    newest = await latest(db, template.id)
    if newest is not None and newest.layout == template.draft:
        raise DomainError(CERT_NOTHING_TO_PUBLISH)
    await check_layout(db, template.draft)
    number = (newest.version_no if newest else 0) + 1
    db.add(
        CertTemplateVersion(
            template_id=template.id, version_no=number, layout=template.draft, published_by=p.id
        )
    )
    await db.flush()
    await record(
        db, p.id, "cert_template.publish_version", "cert_template", template.id,
        {"version_no": [None, number]}, label=template.name,
    )  # fmt: skip
    return await detail(db, template)


@router.post("/cert-templates/{template_id}/restore/{version_no}")
async def restore(
    template_id: uuid.UUID, version_no: int, p: Change, version: Version, db: DB
) -> dict[str, Any]:
    template = await get_template(db, template_id)

    async def current() -> dict[str, Any]:
        return await detail(db, template)

    await check_version(db, template, version, "cert_template", current)
    layout = (
        await db.execute(
            select(CertTemplateVersion.layout).where(
                CertTemplateVersion.template_id == template.id,
                CertTemplateVersion.version_no == version_no,
            )
        )
    ).scalar_one_or_none()
    if layout is None:
        raise DomainError(NOT_FOUND)
    if layout != template.draft:
        template.draft = layout
        template.updated_by, template.updated_at = p.id, clock.now()
        await db.flush()
        await record(
            db, p.id, "cert_template.restore", "cert_template", template.id,
            {"restored_from": [None, version_no]}, label=template.name,
        )  # fmt: skip
    return await detail(db, template)


class DraftPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: dict[str, Any]


@router.post("/cert-templates/{template_id}/draft-preview")
async def draft_preview(
    template_id: uuid.UUID,
    body: DraftPreview,
    p: Change,
    db: DB,
    sample: Annotated[str, Query(pattern="^(short|long|female)$")] = "short",
) -> Response:
    """An unsaved layout from the editor rendered with sample data. Nothing is written."""
    assert sample in SAMPLE_KINDS
    template = await get_template(db, template_id)
    layout = await check_layout(db, body.layout)
    ctx = apply_settings(sample_context(sample), await load_settings(db), template.lang)
    refs = [*layout.asset_refs(), *[r for r in (ctx.signature_ref, ctx.seal_ref) if r]]
    pdf = await render_pdf(layout, ctx, await load_assets(db, refs))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{template.key}_draft_{sample}.pdf"'},
    )


# ---- images ----------------------------------------------------------------------------------


def asset_out(a: CertAsset) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "mime": a.mime,
        "width_px": a.width_px,
        "height_px": a.height_px,
        "size_bytes": a.size_bytes,
    }


def _check_sides(data: bytes) -> None:
    mime, w, h, _ = inspect(data)
    if mime != "image/svg+xml" and ((w or 0) > MAX_SIDE_PX or (h or 0) > MAX_SIDE_PX):
        raise DomainError(CERT_ASSET_INVALID, reason="dimensions")


@router.post("/cert-assets")
async def upload_asset(
    p: Change,
    db: DB,
    file: Annotated[UploadFile, File()],
    kind: Annotated[Literal["background", "image"], Form()],
) -> dict[str, Any]:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DomainError(CERT_ASSET_INVALID, reason="too_large")
    await anyio.to_thread.run_sync(_check_sides, data)
    asset, _ = await store_asset(db, data, kind, p.id)
    await record(
        db, p.id, "cert_asset.upload", "cert_asset", asset.id, {"kind": [None, kind]},
        label="изображение",
    )  # fmt: skip
    return asset_out(asset)


@router.get("/cert-assets/{asset_id}")
async def get_asset(asset_id: uuid.UUID, p: View, db: DB) -> Response:
    asset = await db.get(CertAsset, asset_id)
    if asset is None or asset.kind not in SERVED_KINDS:
        raise DomainError(NOT_FOUND)
    return Response(
        asset.data,
        media_type=asset.mime,
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    )


# ---- catalog and fonts -----------------------------------------------------------------------


def _sample_values(kind: str) -> dict[str, str]:
    ctx = sample_context(kind)
    out = {k: (v.isoformat() if isinstance(v, date) else str(v)) for k, v in ctx.values.items()}
    out["gender"] = ctx.gender or ""
    return out


@router.get("/cert-fields")
async def cert_fields(p: View, db: DB) -> dict[str, Any]:
    samples = {kind: _sample_values(kind) for kind in SAMPLE_KINDS}
    director = await load_settings(db)
    return {
        "fields": [
            {
                "key": key,
                "label": label,
                "group": GROUPS[key.split(".")[0]],
                "type": "date" if key in DATE_KEYS else "text",
                "sample": samples["short"].get(key, ""),
            }
            for key, label in FIELDS.items()
        ],
        "samples": samples,
        "director_by_lang": {
            lang: dict(zip(("name", "title"), director_for(director, lang), strict=True))
            for lang in ("ru", "en", "tg")
        },
        "fonts": [
            {
                "family": family,
                "weights": list(sets[False]),
                "italic_weights": list(sets[True]),
            }
            for family, sets in FAMILIES.items()
        ],
        "date_formats": list(DATE_FORMATS),
        "date_format_examples": {f: format_date(date(2026, 11, 18), f) for f in DATE_FORMATS},
    }


@router.get("/cert-fonts/{file}")
async def get_font(file: str, p: View) -> Response:
    if file not in {name for *_, name in font_files()}:
        raise DomainError(NOT_FOUND)
    return Response(
        (FONT_DIR / file).read_bytes(),
        media_type="font/ttf",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


# ---- rules -----------------------------------------------------------------------------------


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: uuid.UUID
    instructor_id: uuid.UUID | None = None
    template_id: uuid.UUID


class RulesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[RuleIn] = Field(max_length=500)


async def _rules_out(db: AsyncSession) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(
                CertTemplateRule.course_id,
                Course.name,
                CertTemplateRule.instructor_id,
                AppUser.full_name,
                CertTemplateRule.template_id,
                CertTemplate.name,
            )
            .join(Course, Course.id == CertTemplateRule.course_id)
            .join(CertTemplate, CertTemplate.id == CertTemplateRule.template_id)
            .outerjoin(AppUser, AppUser.id == CertTemplateRule.instructor_id)
            .order_by(Course.name, AppUser.full_name.nulls_first())
        )
    ).all()
    return {
        "rules": [
            {
                "course_id": c,
                "course_name": cn,
                "instructor_id": i,
                "instructor_name": inn,
                "template_id": t,
                "template_name": tn,
            }
            for c, cn, i, inn, t, tn in rows
        ]
    }


@router.get("/cert-template-rules")
async def list_rules(p: View, db: DB) -> dict[str, Any]:
    return await _rules_out(db)


@router.put("/cert-template-rules")
async def replace_rules(body: RulesIn, p: Change, db: DB) -> dict[str, Any]:
    targets = [(r.course_id, r.instructor_id) for r in body.rules]
    if len(set(targets)) != len(targets):
        raise DomainError(CERT_RULE_DUPLICATE)

    async def missing(model: Any, ids: set[uuid.UUID], *where: Any) -> bool:
        found = (await db.execute(select(model.id).where(model.id.in_(ids), *where))).scalars()
        return len(set(found)) != len(ids)

    courses = {r.course_id for r in body.rules}
    people = {r.instructor_id for r in body.rules if r.instructor_id}
    templates = {r.template_id for r in body.rules}
    if (
        (courses and await missing(Course, courses))
        or (people and await missing(AppUser, people))
        or (templates and await missing(CertTemplate, templates, CertTemplate.status == "active"))
    ):
        raise DomainError(CERT_RULE_INVALID)
    before = len((await _rules_out(db))["rules"])
    await db.execute(delete(CertTemplateRule))
    db.add_all(
        CertTemplateRule(
            course_id=r.course_id, instructor_id=r.instructor_id, template_id=r.template_id
        )
        for r in body.rules
    )
    await db.flush()
    await record(
        db, p.id, "cert_template_rule.replace", "cert_template_rule", None,
        {"count": [before, len(body.rules)]}, label="правила",
    )  # fmt: skip
    return await _rules_out(db)
