"""Layout + context -> HTML (absolute positions in mm) -> PDF with WeasyPrint.

Safety: template text and field values are HTML-escaped and never evaluated; colors and fonts
are validated by the layout schema; the renderer fetches only `asset:` (images of this
render), `qr:` (generated here), `font:` (bundled files) and small `data:` images inside SVGs.
Any other URL (http, https, file ...) is refused.

Shrink-to-fit measures text with the advances of the same font file (no kerning, a 3% safety
margin on the width), greedy word wrap, explicit line breaks respected.
"""

import html
import io
import os
import threading
from datetime import date
from urllib.parse import unquote

import anyio
import segno
from weasyprint import HTML
from weasyprint.urls import FatalURLFetchingError, URLFetcher, URLFetcherResponse

from app.certificates.errors import (
    CERT_ASSET_INVALID,
    CERT_ASSET_MISSING,
    CERT_GENDER_MISSING,
    CERT_PDF_TOO_LARGE,
    CERT_RENDER_TIMEOUT,
    CERT_TEXT_OVERFLOW,
)
from app.certificates.fields import Context, format_date
from app.certificates.fonts import DIR as FONT_DIR
from app.certificates.fonts import face, font_files, nearest_weight
from app.certificates.layout import (
    AssetSource,
    FieldRun,
    GenderRun,
    ImageLayer,
    Layout,
    LineLayer,
    QrLayer,
    RectLayer,
    SignatureSource,
    TextLayer,
    TextRun,
)
from app.core.config import settings
from app.core.errors import DomainError

PT_PER_MM = 72 / 25.4
WIDTH_MARGIN = 0.97
STEP_PT = 0.5
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_DATA_URL_BYTES = 5 * 1024 * 1024
RENDER_TIMEOUT_S = 15.0
MAX_CONCURRENT = 2
# also holds a render whose request already timed out, so the limit is real
_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT)

Assets = dict[str, tuple[str, bytes]]  # ref -> (mime, bytes)


class Fetcher(URLFetcher):  # type: ignore[misc]
    """Serves the internal schemes of one render; refuses everything else."""

    def __init__(self, resources: dict[str, tuple[str, bytes]]) -> None:
        super().__init__(fail_on_errors=True)
        self.resources = resources

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> URLFetcherResponse:
        scheme = url.split(":", 1)[0].lower() if ":" in url else ""
        if scheme == "font":
            name = unquote(url[5:])
            if "/" in name or "\\" in name or not name.endswith(".ttf"):
                raise ValueError("bad font name")
            known = {f[3] for f in font_files()}
            if name not in known:
                raise ValueError("unknown font")
            return URLFetcherResponse(
                url, (FONT_DIR / name).read_bytes(), {"Content-Type": "font/ttf"}
            )
        if scheme in ("asset", "qr"):
            found = self.resources.get(url)
            if found is None:
                raise ValueError("unknown resource")
            return URLFetcherResponse(url, found[1], {"Content-Type": found[0]})
        if scheme == "data" and len(url) <= MAX_DATA_URL_BYTES:
            return super().fetch(url, headers)
        raise ValueError(f"URL not allowed: {scheme or 'relative'}")


# ---- text -----------------------------------------------------------------------------------


def resolve_text(layer: TextLayer, ctx: Context) -> str:
    """The layer's runs as one string ("\\n" = line break)."""
    out: list[str] = []
    for run in layer.content:
        if isinstance(run, TextRun):
            out.append(run.text)
        elif isinstance(run, FieldRun):
            value = ctx.values.get(run.field, "")
            out.append(format_date(value, run.format) if isinstance(value, date) else value)
        elif isinstance(run, GenderRun):
            if ctx.gender not in ("male", "female"):
                raise DomainError(CERT_GENDER_MISSING, layer=layer.id)
            out.append(getattr(run.gender, ctx.gender))
    text = "".join(out)
    return text.upper() if layer.style.uppercase else text


def text_width_pt(text: str, layer: TextLayer, size_pt: float) -> float:
    st = layer.style
    f = face(st.font, st.weight, st.italic)
    return sum(f.advance(ch) for ch in text) * size_pt + st.letter_spacing_pt * len(text)


def wrap(text: str, layer: TextLayer, size_pt: float) -> list[str] | None:
    """Greedy word wrap to the layer's width; None when a single word is wider than the box."""
    limit = layer.w_mm * PT_PER_MM * WIDTH_MARGIN
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            if text_width_pt(word, layer, size_pt) > limit:
                return None
            trial = f"{current} {word}" if current else word
            if current and text_width_pt(trial, layer, size_pt) > limit:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines


def fits(text: str, layer: TextLayer, size_pt: float) -> bool:
    lines = wrap(text, layer, size_pt)
    return lines is not None and len(lines) * size_pt * layer.style.line_height <= (
        layer.h_mm * PT_PER_MM
    )


def fit_size(text: str, layer: TextLayer) -> float:
    """The font size to draw with. A layer whose min_size_pt is below size_pt shrinks in 0.5 pt
    steps to the largest size that fits; if even the minimum does not, 409 `cert_text_overflow`.
    A fixed-size layer is drawn as it is."""
    st = layer.style
    assert st.min_size_pt is not None
    if st.min_size_pt >= st.size_pt:
        return st.size_pt
    size = st.size_pt
    while size >= st.min_size_pt:
        if fits(text, layer, size):
            return size
        size -= STEP_PT
    if fits(text, layer, st.min_size_pt):
        return st.min_size_pt
    raise DomainError(CERT_TEXT_OVERFLOW, layer=layer.id)


# ---- html -----------------------------------------------------------------------------------


def _n(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _box(layer: TextLayer | ImageLayer | QrLayer | LineLayer | RectLayer) -> str:
    css = (
        f"position:absolute;left:{_n(layer.x_mm)}mm;top:{_n(layer.y_mm)}mm;"
        f"width:{_n(layer.w_mm)}mm;height:{_n(layer.h_mm)}mm;"
    )
    if layer.rotation:
        css += f"transform:rotate({_n(layer.rotation)}deg);transform-origin:50% 50%;"
    return css


def _text_html(layer: TextLayer, ctx: Context) -> str:
    st = layer.style
    text = resolve_text(layer, ctx)
    size = fit_size(text, layer)
    weight, italic = nearest_weight(st.font, st.weight, st.italic)
    lines = "<br>".join(html.escape(line) for line in text.split("\n"))
    cell = (
        f"display:table-cell;vertical-align:{st.valign};"
        f"text-align:{st.align};font-family:'{st.font}';font-weight:{weight};"
        f"font-style:{'italic' if italic else 'normal'};font-size:{_n(size)}pt;"
        f"line-height:{_n(st.line_height)};letter-spacing:{_n(st.letter_spacing_pt)}pt;"
        f"color:{st.color};"
    )
    return (
        f'<div style="{_box(layer)}"><div style="display:table;width:100%;height:100%">'
        f'<div style="{cell}">{lines}</div></div></div>'
    )


def _qr_url(ctx: Context) -> str:
    # The code is the certificate number for now; the registry stage replaces it with a random
    # verify code stored per certificate.
    base = settings.cert_verify_base_url.rstrip("/")
    return f"{base}/v/{ctx.verify_code}"


def _qr_svg(url: str, color: str) -> bytes:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", dark=color, light=None, border=0, scale=1)
    return buf.getvalue()


def build_html(
    layout: Layout, ctx: Context, assets: Assets
) -> tuple[str, dict[str, tuple[str, bytes]]]:
    """(html, internal resources by URL). Raises the template errors (gender, overflow, asset)."""
    resources: dict[str, tuple[str, bytes]] = {}

    def asset(ref: str) -> str:
        if ref not in assets:
            raise DomainError(CERT_ASSET_MISSING, asset=ref)
        resources[f"asset:{ref}"] = assets[ref]
        return f"asset:{ref}"

    page = layout.page
    body: list[str] = []
    faces: set[tuple[str, int, bool]] = set()
    if layout.background:
        body.append(
            f'<img src="{html.escape(asset(layout.background.asset))}" '
            'style="position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover">'
        )
    for i, layer in enumerate(layout.layers):
        if isinstance(layer, TextLayer):
            body.append(_text_html(layer, ctx))
            w, it = nearest_weight(layer.style.font, layer.style.weight, layer.style.italic)
            faces.add((layer.style.font, w, it))
        elif isinstance(layer, ImageLayer):
            if isinstance(layer.source, AssetSource):
                src = html.escape(asset(layer.source.asset))
                body.append(f'<img src="{src}" style="{_box(layer)}object-fit:contain">')
            elif isinstance(layer.source, SignatureSource):
                # samples carry no instructor, so nothing is drawn for it there
                ref = (
                    ctx.signature_ref
                    if layer.source.signature == "director"
                    else ctx.instructor_signature_ref
                )
                if ref and ref in assets:
                    body.append(
                        f'<img src="{html.escape(asset(ref))}" '
                        f'style="{_box(layer)}object-fit:contain">'
                    )
            elif ctx.seal_ref and ctx.seal_ref in assets:
                body.append(
                    f'<img src="{html.escape(asset(ctx.seal_ref))}" '
                    f'style="{_box(layer)}object-fit:contain">'
                )
        elif isinstance(layer, QrLayer):
            key = f"qr:{i}"
            resources[key] = ("image/svg+xml", _qr_svg(_qr_url(ctx), layer.color))
            body.append(f'<img src="{key}" style="{_box(layer)}object-fit:contain">')
        elif isinstance(layer, RectLayer):
            body.append(f'<div style="{_box(layer)}background:{layer.fill}"></div>')
        elif isinstance(layer, LineLayer):
            style = "dashed" if layer.dash else "solid"
            body.append(
                f'<div style="{_box(layer)}height:0;border-top:{_n(layer.thickness_mm)}mm '
                f'{style} {layer.color}"></div>'
            )
    font_css = "".join(
        f"@font-face{{font-family:'{fam}';font-weight:{w};"
        f"font-style:{'italic' if it else 'normal'};"
        f"src:url('font:{fam}-{w}{'Italic' if it else ''}.ttf')}}"
        for fam, w, it in sorted(faces)
    )
    w_mm, h_mm = _n(page.width_mm), _n(page.height_mm)
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        f"@page{{size:{w_mm}mm {h_mm}mm;margin:0}}{font_css}"
        "html,body{margin:0;padding:0}"
        f"body{{position:relative;width:{w_mm}mm;height:{h_mm}mm;overflow:hidden}}"
        f"</style></head><body>{''.join(body)}</body></html>"
    )
    return doc, resources


def render_sync(layout: Layout, ctx: Context, assets: Assets) -> bytes:
    # font subsets carry a modified-time stamp (fontTools reads this variable): fixed, the same
    # certificate renders to the same bytes every time
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1767225600")
    with _SLOTS:
        doc, resources = build_html(layout, ctx, assets)
        try:
            pdf = HTML(string=doc, url_fetcher=Fetcher(resources)).write_pdf()
        except FatalURLFetchingError:
            raise DomainError(CERT_ASSET_INVALID, reason="unreadable") from None
    if len(pdf) > MAX_PDF_BYTES:
        raise DomainError(CERT_PDF_TOO_LARGE)
    return bytes(pdf)


async def render_pdf(layout: Layout, ctx: Context, assets: Assets) -> bytes:
    """PDF bytes, rendered in a worker thread: at most 2 at a time, 15 s each."""
    try:
        with anyio.fail_after(RENDER_TIMEOUT_S):
            return await anyio.to_thread.run_sync(
                render_sync, layout, ctx, assets, abandon_on_cancel=True
            )
    except TimeoutError:
        raise DomainError(CERT_RENDER_TIMEOUT) from None
