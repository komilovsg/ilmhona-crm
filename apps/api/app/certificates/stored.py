"""Render an issued certificate from what was stored at issue: the exact template version and the
snapshot of values, so the PDF is the same whatever changed since."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates.assets import load_assets
from app.certificates.errors import CERT_NO_TEMPLATE
from app.certificates.fields import context_of, image_refs
from app.certificates.layout import parse_layout
from app.certificates.render import render_pdf
from app.core.errors import DomainError
from app.models import Certificate, CertTemplateVersion


async def render_certificate(db: AsyncSession, cert: Certificate) -> bytes:
    version = await db.get(CertTemplateVersion, cert.template_version_id)
    if version is None:
        raise DomainError(CERT_NO_TEMPLATE)
    layout = parse_layout(version.layout)
    ctx = context_of(cert.data)
    assets = await load_assets(db, [*layout.asset_refs(), *image_refs(ctx)])
    return await render_pdf(layout, ctx, assets)
