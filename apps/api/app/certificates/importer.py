"""`python -m app.cli import-cert-templates`: layouts + images from disk into the database.

The layouts live in the repo (`app/certificates/seed/`); the images are company files kept out
of it. `background.asset` and image `asset` in a layout file are file names relative to the
images directory; here they become `cert_asset` ids. Safe to run again: identical images are
stored once, an unchanged layout publishes nothing.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.certificates.assets import store_asset
from app.certificates.fields import load_settings
from app.certificates.layout import Layout, parse_layout
from app.certificates.signature import clean as clean_image
from app.core.errors import DomainError
from app.models import AppUser, CertTemplate, CertTemplateVersion

MANIFEST = "templates.json"
SETTINGS_FILE = "settings.json"
INSTRUCTORS_FILE = "instructors.json"


class ImportProblem(Exception):
    pass


@dataclass
class Counts:
    assets_created: int = 0
    templates_created: int = 0
    templates_updated: int = 0
    versions_published: int = 0
    settings_changed: int = 0
    signatures_assigned: int = 0
    signatures_unmatched: list[str] = field(default_factory=list)


def _read_manifest(layouts: Path) -> list[dict[str, Any]]:
    path = layouts / MANIFEST
    if not path.is_file():
        raise ImportProblem(f"{path} not found")
    items = json.loads(path.read_text())
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ImportProblem(f"{MANIFEST} must be a list of objects")
    for item in items:
        for k in ("key", "name", "layout"):
            if not isinstance(item.get(k), str) or not item[k]:
                raise ImportProblem(f"{MANIFEST}: every entry needs {k!r}")
        if item.get("lang", "ru") not in ("ru", "en", "tg"):
            raise ImportProblem(f"{MANIFEST}: bad lang for {item['key']}")
    return items


def _image_file(images: Path, name: str) -> Path:
    path = (images / name).resolve()
    if not path.is_relative_to(images.resolve()) or not path.is_file():
        raise ImportProblem(f"image not found: {name}")
    return path


def load_layouts(layouts: Path) -> list[tuple[dict[str, Any], Layout]]:
    parsed: list[tuple[dict[str, Any], Layout]] = []
    for item in _read_manifest(layouts):
        file = layouts / item["layout"]
        if not file.is_file() or not file.resolve().is_relative_to(layouts.resolve()):
            raise ImportProblem(f"layout not found: {item['layout']}")
        try:
            parsed.append((item, parse_layout(json.loads(file.read_text()))))
        except DomainError as exc:
            raise ImportProblem(f"{item['layout']}: {exc.error.code} {exc.params}") from None
    return parsed


async def import_templates(db: AsyncSession, layouts: Path, images: Path) -> Counts:
    counts = Counts()
    parsed = load_layouts(layouts)
    for item, layout in parsed:
        mapping: dict[str, str] = {}
        for n, ref in enumerate(layout.asset_refs()):
            if ref in mapping:
                continue
            kind = "background" if layout.background and n == 0 else "image"
            try:
                asset, created = await store_asset(db, _image_file(images, ref).read_bytes(), kind)
            except DomainError as exc:
                raise ImportProblem(f"{ref}: {exc.error.code} {exc.params}") from None
            counts.assets_created += created
            mapping[ref] = str(asset.id)
        draft = layout.map_assets(mapping).dump()
        lang = item.get("lang", "ru")
        template = (
            await db.execute(select(CertTemplate).where(CertTemplate.key == item["key"]))
        ).scalar_one_or_none()
        if template is None:
            template = CertTemplate(key=item["key"], name=item["name"], lang=lang, draft=draft)
            db.add(template)
            await db.flush()
            counts.templates_created += 1
        elif (template.draft, template.name, template.lang) != (draft, item["name"], lang):
            template.draft, template.name, template.lang = draft, item["name"], lang
            template.updated_at = func.now()
            await db.flush()
            counts.templates_updated += 1
        latest = (
            await db.execute(
                select(CertTemplateVersion.version_no, CertTemplateVersion.layout)
                .where(CertTemplateVersion.template_id == template.id)
                .order_by(CertTemplateVersion.version_no.desc())
                .limit(1)
            )
        ).first()
        if latest is None or latest.layout != draft:
            number = (latest.version_no if latest else 0) + 1
            db.add(CertTemplateVersion(template_id=template.id, version_no=number, layout=draft))
            await db.flush()
            counts.versions_published += 1
            await record(
                db,
                None,
                "cert_template.publish",
                "cert_template",
                template.id,
                {"version": [None, number], "cli": [None, "import-cert-templates"]},
            )
    await import_settings(db, images, counts)
    await import_instructor_signatures(db, images, counts)
    return counts


def _name_key(name: str) -> tuple[str, ...]:
    """A name as a set of lowercase words: «Бобоев Джамшед» and «Джамшед Бобоев» are one."""
    return tuple(sorted(name.lower().replace("ё", "е").split()))


async def import_instructor_signatures(db: AsyncSession, images: Path, counts: Counts) -> None:
    """`instructors.json` of the images directory (optional): `[{"full_name": ..., "signature":
    <image file>}]`. The signature goes to the user with that name (either word order); a name
    that matches nobody (or several people) is reported, not an error. A user who already has a
    signature keeps it, so a signature set in the CRM is never replaced."""
    path = images / INSTRUCTORS_FILE
    if not path.is_file():
        return
    items = json.loads(path.read_text())
    if not isinstance(items, list) or not all(
        isinstance(i, dict) and isinstance(i.get("full_name"), str) and i.get("signature")
        for i in items
    ):
        raise ImportProblem(f"{INSTRUCTORS_FILE}: expected a list of {{full_name, signature}}")
    users: dict[tuple[str, ...], list[AppUser]] = {}
    for user in (await db.execute(select(AppUser))).scalars():
        users.setdefault(_name_key(user.full_name), []).append(user)
    for item in items:
        found = users.get(_name_key(item["full_name"]), [])
        if len(found) != 1:
            counts.signatures_unmatched.append(item["full_name"])
            continue
        user = found[0]
        if user.signature_asset_id is not None:
            continue
        try:
            asset, created = await store_asset(
                db, clean_image(_image_file(images, item["signature"]).read_bytes()), "signature"
            )
        except DomainError as exc:
            raise ImportProblem(f"{item['signature']}: {exc.error.code} {exc.params}") from None
        counts.assets_created += created
        user.signature_asset_id = asset.id
        await db.flush()
        counts.signatures_assigned += 1
        await record(
            db, None, "instructor.signature_upload", "app_user", user.id,
            {"signature": [None, asset.id], "cli": [None, "import-cert-templates"]},
            branch_id=user.branch_id, label=user.full_name,
        )  # fmt: skip


async def import_settings(db: AsyncSession, images: Path, counts: Counts) -> None:
    """`settings.json` of the images directory (optional): the director's name, title,
    signature and seal. A value already in place changes nothing, so a re-run is silent."""
    path = images / SETTINGS_FILE
    if not path.is_file():
        return
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) - {
        "director_name", "director_title", "signature", "seal"
    }:  # fmt: skip
        raise ImportProblem(
            f"{SETTINGS_FILE}: expected director_name, director_title, signature, seal"
        )
    row = await load_settings(db)
    if row.updated_by is not None:
        # someone already set the director in the CRM: the import file must not undo it
        return
    before: dict[str, str | None] = {
        "director_name": row.director_name,
        "director_title": row.director_title,
        "signature": str(row.director_signature_asset_id or "") or None,
        "seal": str(row.seal_asset_id) if row.seal_asset_id else None,
    }  # fmt: skip
    after = dict(before)
    for key in ("director_name", "director_title"):
        if key in data:
            if not isinstance(data[key], str):
                raise ImportProblem(f"{SETTINGS_FILE}: {key} must be text")
            after[key] = data[key].strip()
    for key, kind in (("signature", "signature"), ("seal", "seal")):
        if data.get(key):
            try:
                asset, created = await store_asset(
                    db, clean_image(_image_file(images, data[key]).read_bytes()), kind
                )
            except DomainError as exc:
                raise ImportProblem(f"{data[key]}: {exc.error.code} {exc.params}") from None
            counts.assets_created += created
            after[key] = str(asset.id)
    diff = diff_of(before, after)
    if not diff:
        return
    row.director_name = after["director_name"] or ""
    row.director_title = after["director_title"] or ""
    row.director_signature_asset_id = uuid.UUID(after["signature"]) if after["signature"] else None
    row.seal_asset_id = uuid.UUID(after["seal"]) if after["seal"] else None
    await db.flush()
    counts.settings_changed += 1
    await record(
        db, None, "cert_settings.update", "cert_settings", str(row.id), diff,
        label="настройки сертификатов",
    )  # fmt: skip
