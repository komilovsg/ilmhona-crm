"""Certificate images: type sniffing, size, SVG sanitising, storage deduplicated by sha256."""

import hashlib
import io
import re
import uuid
import xml.etree.ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates.errors import CERT_ASSET_INVALID
from app.core.errors import DomainError
from app.models import CertAsset

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
KINDS = ("background", "signature", "seal", "logo", "image")
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
_DROP_TAGS = {
    "script",
    "foreignobject",
    "iframe",
    "object",
    "embed",
    "audio",
    "video",
    "animate",
    "set",
}
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$")
_CSS_URL = re.compile(r"url\(\s*['\"]?\s*([^)'\"]*)", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _safe_href(value: str) -> bool:
    v = value.strip()
    return v.startswith("#") or bool(_DATA_IMAGE.match(v))


def _safe_css(css: str) -> str | None:
    """None when the CSS reaches outside the file (@import, url() that is not local)."""
    if re.search(r"@import|expression\(|javascript:", css, re.I):
        return None
    for m in _CSS_URL.finditer(css):
        if not _safe_href(m.group(1)):
            return None
    return css


def _clean(el: ET.Element) -> None:
    for child in list(el):
        if _local(child.tag) in _DROP_TAGS:
            el.remove(child)
            continue
        if _local(child.tag) == "style" and child.text and _safe_css(child.text) is None:
            el.remove(child)
            continue
        _clean(child)
    for name in list(el.attrib):
        key = _local(name)
        value = el.attrib[name]
        if key.startswith("on"):
            del el.attrib[name]
        elif key == "href" and not _safe_href(value):
            del el.attrib[name]
        elif key == "style" and _safe_css(value) is None:
            del el.attrib[name]
        elif key not in ("href", "style") and _CSS_URL.search(value) and _safe_css(value) is None:
            del el.attrib[name]


def sanitize_svg(data: bytes) -> bytes:
    """Drop scripts, foreignObject, event handlers and every reference that leaves the file
    (external hrefs, CSS url()/@import). DTDs and entities are refused outright."""
    try:
        root = SafeET.fromstring(data, forbid_dtd=True)
    except DefusedXmlException, ET.ParseError, ValueError:
        raise DomainError(CERT_ASSET_INVALID, reason="svg_unreadable") from None
    if _local(root.tag) != "svg":
        raise DomainError(CERT_ASSET_INVALID, reason="not_svg")
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    _clean(root)
    return bytes(ET.tostring(root, encoding="utf-8"))


def _svg_size(data: bytes) -> tuple[int | None, int | None]:
    root = SafeET.fromstring(data, forbid_dtd=True)

    def num(v: str | None) -> int | None:
        m = re.match(r"\s*([\d.]+)", v or "")
        return round(float(m.group(1))) if m else None

    w, h = num(root.get("width")), num(root.get("height"))
    if (w is None or h is None) and root.get("viewBox"):
        parts = re.split(r"[\s,]+", root.get("viewBox", "").strip())
        if len(parts) == 4:
            w, h = num(parts[2]), num(parts[3])
    return w, h


def inspect(data: bytes) -> tuple[str, int | None, int | None, bytes]:
    """(mime, width, height, data to store). Sniffs the real type from the bytes; a raster file
    must decode, an SVG is sanitised."""
    if len(data) > MAX_BYTES:
        raise DomainError(CERT_ASSET_INVALID, reason="too_large")
    if data.lstrip()[:5] in (b"<?xml", b"<svg ") or b"<svg" in data[:1024]:
        clean = sanitize_svg(data)
        w, h = _svg_size(clean)
        return "image/svg+xml", w, h, clean
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            fmt, size = img.format, img.size
    except UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError:
        raise DomainError(CERT_ASSET_INVALID, reason="unreadable") from None
    mime = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(fmt or "")
    if mime is None:
        raise DomainError(CERT_ASSET_INVALID, reason="type")
    return mime, size[0], size[1], data


async def store_asset(
    db: AsyncSession, data: bytes, kind: str, uploaded_by: uuid.UUID | None = None
) -> tuple[CertAsset, bool]:
    """(asset, created). The same bytes (after sanitising) are stored once."""
    if kind not in KINDS:
        raise DomainError(CERT_ASSET_INVALID, reason="kind")
    mime, w, h, clean = inspect(data)
    digest = hashlib.sha256(clean).hexdigest()
    found = (
        await db.execute(select(CertAsset).where(CertAsset.sha256 == digest))
    ).scalar_one_or_none()
    if found is not None:
        return found, False
    asset = CertAsset(
        kind=kind, mime=mime, data=clean, sha256=digest, size_bytes=len(clean),
        width_px=w, height_px=h, uploaded_by=uploaded_by,
    )  # fmt: skip
    db.add(asset)
    await db.flush()
    return asset, True


async def load_assets(db: AsyncSession, refs: list[str]) -> dict[str, tuple[str, bytes]]:
    """{ref: (mime, bytes)} for every ref that is a stored asset id; others are left out."""
    ids: dict[uuid.UUID, str] = {}
    for ref in refs:
        try:
            ids[uuid.UUID(ref)] = ref
        except ValueError:
            continue
    if not ids:
        return {}
    rows = (await db.execute(select(CertAsset).where(CertAsset.id.in_(list(ids))))).scalars()
    return {ids[a.id]: (a.mime, a.data) for a in rows}
