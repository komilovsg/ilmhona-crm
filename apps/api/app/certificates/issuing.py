"""Readiness checks and the snapshot of one certificate (shared by check, issue and reissue)."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates.assets import load_assets
from app.certificates.errors import (
    CERT_ASSET_MISSING,
    CERT_CUSTOM_INVALID,
    CERT_GENDER_MISSING,
    CERT_NO_TEMPLATE,
    CERT_TEXT_OVERFLOW,
)
from app.certificates.fields import (
    DATE_KEYS,
    FIELDS,
    Context,
    enrollment_context,
    image_refs,
    snapshot_of,
)
from app.certificates.layout import ImageLayer, Layout, SignatureSource, parse_layout
from app.certificates.render import Assets, build_html
from app.core import clock
from app.core.errors import NOT_FOUND, DomainError
from app.models import AppUser, CertSettings, CertTemplate, CertTemplateVersion, Cohort, Enrollment

LANGS = ("ru", "en", "tg")
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 12
PLACEHOLDER_NUMBER = "CERT-0000-0000"
MAX_CUSTOM = 200

FIX_TEXTS = {
    "not_graduate": "Студент не выпускник",
    "no_gender": "Не указан пол студента: шаблон требует его",
    "name_overflow": "Текст не помещается в блок шаблона",
    "missing_signature": "Нет подписи, которую требует шаблон",
    "asset_missing": "Не найдено изображение шаблона",
}


def new_verify_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


@dataclass
class Fix:
    code: str
    text: str


async def published_version(db: AsyncSession, template: CertTemplate) -> CertTemplateVersion:
    version = (
        await db.execute(
            select(CertTemplateVersion)
            .where(CertTemplateVersion.template_id == template.id)
            .order_by(CertTemplateVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version is None or template.status != "active":
        raise DomainError(CERT_NO_TEMPLATE)
    return version


async def chosen_template(db: AsyncSession, template_id: uuid.UUID) -> CertTemplate:
    template = await db.get(CertTemplate, template_id)
    if template is None:
        raise DomainError(NOT_FOUND)
    return template


def clean_custom(custom: dict[str, str] | None) -> dict[str, str]:
    """Hand-typed values for catalog fields (the number is never one of them)."""
    out: dict[str, str] = {}
    for key, value in (custom or {}).items():
        text = value.strip() if isinstance(value, str) else None
        if key not in FIELDS or key == "certificate.number" or text is None:
            raise DomainError(CERT_CUSTOM_INVALID, field=key)
        if len(text) > MAX_CUSTOM:
            raise DomainError(CERT_CUSTOM_INVALID, field=key)
        if key in DATE_KEYS:
            try:
                date.fromisoformat(text)
            except ValueError:
                raise DomainError(CERT_CUSTOM_INVALID, field=key) from None
        out[key] = text
    return out


def apply_custom(ctx: Context, custom: dict[str, str]) -> None:
    for key, value in custom.items():
        ctx.values[key] = date.fromisoformat(value) if key in DATE_KEYS else value


class AssetCache:
    """Images of a batch: the background is loaded once, an instructor's signature once."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.assets: Assets = {}

    async def get(self, refs: list[str]) -> Assets:
        missing = [r for r in refs if r not in self.assets]
        if missing:
            self.assets.update(await load_assets(self.db, missing))
        return {r: self.assets[r] for r in refs if r in self.assets}


def missing_signature(layout: Layout, ctx: Context, assets: Assets) -> bool:
    for layer in layout.layers:
        if isinstance(layer, ImageLayer) and isinstance(layer.source, SignatureSource):
            ref = (
                ctx.signature_ref
                if layer.source.signature == "director"
                else ctx.instructor_signature_ref
            )
            if not ref or ref not in assets:
                return True
    return False


def fix_of(layout: Layout, ctx: Context, assets: Assets) -> Fix | None:
    """The first reason this context cannot be rendered with the layout, or None."""
    if missing_signature(layout, ctx, assets):
        return Fix("missing_signature", FIX_TEXTS["missing_signature"])
    try:
        build_html(layout, ctx, assets)
    except DomainError as exc:
        codes = {
            CERT_GENDER_MISSING: "no_gender",
            CERT_TEXT_OVERFLOW: "name_overflow",
            CERT_ASSET_MISSING: "asset_missing",
        }
        if exc.error in codes:
            return Fix(codes[exc.error], FIX_TEXTS[codes[exc.error]])
        raise
    return None


@dataclass
class Prepared:
    ctx: Context
    cohort: Cohort
    instructor: AppUser | None
    enrollment: Enrollment
    assets: Assets


async def prepare(
    db: AsyncSession,
    enrollment_id: uuid.UUID,
    layout: Layout,
    lang: str,
    custom: dict[str, str],
    cache: AssetCache,
    settings_row: CertSettings,
    number: str | None = None,
) -> Prepared:
    """The context of a certificate issued now: the number (a placeholder of the same width until
    one is given), today's date, the verify code or the number for the QR."""
    ctx, cohort, _course, instructor, enrollment = await enrollment_context(db, enrollment_id, lang)
    number = number or enrollment.certificate_no or PLACEHOLDER_NUMBER
    ctx.values["certificate.number"] = number
    ctx.values["certificate.issued_date"] = clock.now().astimezone(clock.TZ).date()
    base = (settings_row.verify_base_url or "").rstrip("/")
    ctx.verify_base = base
    ctx.verify_code = ""  # the random code is set when the row is created
    apply_custom(ctx, custom)
    assets = await cache.get([*layout.asset_refs(), *image_refs(ctx)])
    return Prepared(ctx, cohort, instructor, enrollment, assets)


def snapshot(
    prep: Prepared, lang: str, custom: dict[str, str], number: str, code: str
) -> dict[str, Any]:
    prep.ctx.values["certificate.number"] = number
    prep.ctx.verify_code = code if prep.ctx.verify_base else number
    return snapshot_of(prep.ctx, lang, custom)


def layout_of(version: CertTemplateVersion) -> Layout:
    return parse_layout(version.layout)
