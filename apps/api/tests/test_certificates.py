"""Certificates C1: layout schema, renderer (limits, escaping, fetcher, fit), PDF endpoints,
template import, SVG sanitising."""

import io
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fontTools.ttLib import TTFont
from pypdf import PdfReader

from app.certificates import render
from app.certificates.assets import inspect, sanitize_svg
from app.certificates.fields import Context, format_date, sample_context, split_name
from app.certificates.fonts import DIR as FONT_DIR
from app.certificates.fonts import font_files
from app.certificates.importer import ImportProblem, import_templates
from app.certificates.layout import TextLayer, parse_layout
from app.core.db import sessionmaker
from app.core.errors import DomainError
from tests.certs import (
    GENERAL,
    SVG,
    layout,
    make_template,
    png,
    text_layer,
    with_layers,
)  # fmt: skip
from tests.conftest import SignedIn, make_role, sql
from tests.reports import G, finished_cohort

MM = 72 / 25.4


@pytest.fixture(autouse=True)
async def fresh_certificate_numbers() -> Any:
    """Other tests expect CERT-<year>-0001 from a fresh sequence."""
    yield
    await sql("ALTER SEQUENCE certificate_no_seq RESTART")


def codes(exc: pytest.ExceptionInfo[DomainError]) -> tuple[int, str]:
    return exc.value.error.status, exc.value.error.code


def pdf_text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


ASSETS = {"bg": ("image/png", png())}


def seed_like() -> dict[str, Any]:
    return layout("bg")


# ---- layout schema ---------------------------------------------------------------------------


def test_a_seed_like_layout_passes() -> None:
    lay = parse_layout(seed_like())
    assert len(lay.layers) == 6 and lay.asset_refs() == ["bg"]
    assert lay.layers[0].style.min_size_pt == 36  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda d: d["layers"][0]["content"].append({"field": "student.passport"}), "cert_field_unknown"),
        (lambda d: d.update(layers=[d["layers"][1]] * 41), "cert_layout_invalid"),
        (lambda d: d["layers"][0]["style"].update(color="red"), "cert_layout_invalid"),
        (lambda d: d["layers"][0].update(id="Bad Id"), "cert_layout_invalid"),
        (lambda d: d["layers"][0].update(surprise=1), "cert_layout_invalid"),
        (lambda d: d["layers"][0]["style"].update(font="Comic Sans"), "cert_layout_invalid"),
        (lambda d: d["page"].update(width_mm=10), "cert_layout_invalid"),
        (lambda d: d["layers"][1].update(id="name"), "cert_layout_invalid"),
        (lambda d: d["layers"][0]["style"].update(min_size_pt=99), "cert_layout_invalid"),
        (lambda d: d["layers"][0]["content"].append({"text": "x" * 1001}), "cert_layout_invalid"),
        (lambda d: d["layers"][0]["content"].append({"field": "course.name", "format": "yy"}), "cert_layout_invalid"),
        (lambda d: d["layers"][0]["content"].append({"text": "a", "field": "course.name"}), "cert_layout_invalid"),
    ],
)  # fmt: skip
def test_a_bad_layout_is_422(change: Any, code: str) -> None:
    data = seed_like()
    change(data)
    with pytest.raises(DomainError) as exc:
        parse_layout(data)
    assert codes(exc) == (422, code)


def test_a_layout_over_200_kb_is_refused() -> None:
    data = seed_like()
    data["layers"][0]["content"] = [{"text": "я" * 900}] * 50
    with pytest.raises(DomainError) as exc:
        parse_layout(data)
    assert exc.value.error.status == 422


# ---- fields ----------------------------------------------------------------------------------


def test_dates_and_names() -> None:
    d = date(2026, 11, 8)
    assert format_date(d, None) == "08.11.2026"
    assert format_date(d, "d month yyyy") == "8 ноября 2026"
    assert format_date(d, "month d, yyyy") == "November 8, 2026"
    assert split_name("Каримов Али Рустамович") == ("Али Рустамович", "Каримов")
    assert split_name("Каримов") == ("", "Каримов")


# ---- fonts -----------------------------------------------------------------------------------


def test_every_bundled_font_has_cyrillic_and_tajik_letters() -> None:
    assert (FONT_DIR / "OFL.txt").is_file()
    for _, _, _, name in font_files():
        cmap = TTFont(FONT_DIR / name).getBestCmap()
        missing = [ch for ch in "ғҳҷӣқӯҒҲҶӢҚӮабвгдЯ" if ord(ch) not in cmap]
        assert missing == [], name


# ---- measuring and fit -----------------------------------------------------------------------


def narrow(w_mm: float, h_mm: float, **style: Any) -> TextLayer:
    lay = parse_layout(
        with_layers(
            {**text_layer("t", **style), "w_mm": w_mm, "h_mm": h_mm, "x_mm": 10, "y_mm": 10}
        )
    )
    layer = lay.layers[0]
    assert isinstance(layer, TextLayer)
    return layer


def test_width_scales_with_size_and_letter_spacing() -> None:
    layer = narrow(100, 20)
    one = render.text_width_pt("Абв", layer, 10)
    assert one > 0
    assert render.text_width_pt("Абв", layer, 20) == pytest.approx(2 * one)
    spaced = narrow(100, 20, letter_spacing_pt=2)
    assert render.text_width_pt("Абв", spaced, 10) == pytest.approx(one + 6)


def test_wrap_is_greedy_and_respects_line_breaks() -> None:
    layer = narrow(40, 50)
    lines = render.wrap("один два три\nчетыре", layer, 12)
    assert lines is not None and lines[-1] == "четыре" and len(lines) >= 2
    assert render.wrap("Сверхдлинноеслововообщенеделящеесянастроки", narrow(20, 50), 30) is None


def test_a_long_name_shrinks_to_fit_and_a_fixed_size_does_not() -> None:
    name = "Абдурахмонзода Мухаммадджон"
    shrinking = narrow(80, 20, size_pt=40, min_size_pt=16)
    size = render.fit_size(name, shrinking)
    assert 16 <= size < 40 and render.fits(name, shrinking, size)
    assert not render.fits(name, shrinking, size + 0.5) or size == 40
    assert render.fit_size(name, narrow(80, 20, size_pt=40)) == 40  # no min_size_pt: as is
    assert render.fit_size("Али", shrinking) == 40  # fits as it is


def test_text_that_cannot_fit_even_at_the_minimum_overflows() -> None:
    layer = narrow(30, 8, size_pt=40, min_size_pt=30)
    with pytest.raises(DomainError) as exc:
        render.fit_size("Абдурахмонзода Мухаммадджон", layer)
    assert codes(exc) == (409, "cert_text_overflow") and exc.value.params["layer"] == "t"


# ---- rendering -------------------------------------------------------------------------------


def draw(lay: dict[str, Any], ctx: Context | None = None, assets: Any = ASSETS) -> bytes:
    return render.render_sync(parse_layout(lay), ctx or sample_context("short"), assets)


def test_the_pdf_has_the_layout_page_size() -> None:
    pdf = draw(seed_like())
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    box = reader.pages[0].mediabox
    assert (float(box.width), float(box.height)) == (
        pytest.approx(297 * MM, abs=0.5),
        pytest.approx(210 * MM, abs=0.5),
    )
    lay = seed_like()
    lay["page"] = {"width_mm": 210, "height_mm": 297}
    box = PdfReader(io.BytesIO(draw(lay))).pages[0].mediabox
    assert float(box.width) == pytest.approx(210 * MM, abs=0.5)


def test_values_are_shown_and_markup_in_a_name_is_escaped() -> None:
    ctx = sample_context("short")
    ctx.values["student.full_name"] = "<script>alert(1)</script> & Ко"
    text = pdf_text(draw(seed_like(), ctx))
    assert "<script>alert(1)</script> & Ко" in text
    assert "CERT-2026-0001" in text and "18 ноября 2026" in text
    html, _ = render.build_html(parse_layout(seed_like()), ctx, ASSETS)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_tajik_letters_are_drawn() -> None:
    ctx = sample_context("female")  # Раҳимова Ҳалимаи Ҷамшед
    text = pdf_text(draw(seed_like(), ctx))
    assert "Раҳимова" in text and "Ҷамшед" in text


def test_the_gender_run_picks_the_word_and_a_missing_gender_is_409() -> None:
    run = {"gender": {"male": "завершил", "female": "завершила"}}
    lay = with_layers(text_layer("g", run))
    assert "завершила" in pdf_text(draw(lay, sample_context("female")))
    assert "завершил" in pdf_text(draw(lay, sample_context("short")))
    ctx = sample_context("short")
    ctx.gender = None
    with pytest.raises(DomainError) as exc:
        draw(lay, ctx)
    assert codes(exc) == (409, "cert_gender_missing")


def test_uppercase_and_a_long_name_that_overflows() -> None:
    lay = with_layers(text_layer("n", uppercase=True))
    assert "КАРИМОВ АЛИ" in pdf_text(draw(lay))
    tight = with_layers({**text_layer("n", size_pt=40, min_size_pt=30), "w_mm": 30, "h_mm": 8})
    with pytest.raises(DomainError) as exc:
        draw(tight, sample_context("long"))
    assert codes(exc) == (409, "cert_text_overflow")


def test_a_missing_asset_is_422() -> None:
    with pytest.raises(DomainError) as exc:
        draw(seed_like(), assets={})
    assert codes(exc) == (422, "cert_asset_missing")


def test_the_fetcher_refuses_everything_but_internal_schemes() -> None:
    f = render.Fetcher({"asset:x": ("image/png", png())})
    for url in (
        "http://169.254.169.254/latest/meta-data",
        "https://example.com/a.png",
        "file:///etc/passwd",
        "ftp://example.com/a",
        "font:../../../etc/passwd",
        "font:Nope.ttf",
        "asset:other",
        "qr:9",
        "javascript:alert(1)",
        "data:image/png;base64," + "A" * (render.MAX_DATA_URL_BYTES + 1),
    ):
        with pytest.raises(ValueError):  # noqa: PT011
            f.fetch(url)
    assert f.fetch("asset:x").read() == png()
    assert f.fetch("font:Montserrat-400.ttf").read()[:4] in (b"\x00\x01\x00\x00", b"true")


def test_a_layout_cannot_make_the_renderer_fetch_a_url() -> None:
    # an http asset ref is only ever looked up in the render's own assets: it is missing, not fetched
    lay = layout("http://127.0.0.1:9/evil.png")
    with pytest.raises(DomainError) as exc:
        draw(lay)
    assert codes(exc) == (422, "cert_asset_missing")


async def test_render_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    def slow(*_: Any) -> bytes:
        time.sleep(1)
        return b""

    monkeypatch.setattr(render, "RENDER_TIMEOUT_S", 0.05)
    monkeypatch.setattr(render, "render_sync", slow)
    with pytest.raises(DomainError) as exc:
        await render.render_pdf(parse_layout(seed_like()), sample_context("short"), ASSETS)
    assert codes(exc) == (503, "cert_render_timeout")


def test_a_huge_pdf_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render, "MAX_PDF_BYTES", 100)
    with pytest.raises(DomainError) as exc:
        draw(seed_like())
    assert exc.value.error.code == "cert_pdf_too_large"


RED = b"0.8 0 0 rg"


def pdf_streams(pdf: bytes) -> bytes:
    """Every decoded stream of the file: page content, forms, images (an SVG icon is drawn as paths)."""
    reader = PdfReader(io.BytesIO(pdf))
    out = b""
    for n in range(1, len(reader.xref_objStm) + 400):
        try:
            obj = reader.get_object(n)
        except Exception:
            continue
        if hasattr(obj, "get_data"):
            out += obj.get_data()
    return out


# ---- images ----------------------------------------------------------------------------------

EVIL_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
 width="10" height="10" onload="alert(1)">
<script>alert(1)</script>
<foreignObject><div>x</div></foreignObject>
<style>@import url(http://evil.example/a.css); rect { fill: red }</style>
<image xlink:href="http://evil.example/a.png" width="1" height="1"/>
<image href="file:///etc/passwd" width="1" height="1"/>
<image href="data:image/png;base64,AAAA" width="1" height="1"/>
<rect width="5" height="5" onclick="x()" style="fill:url(http://evil.example/p)"/>
<a href="javascript:alert(1)"><rect width="1" height="1"/></a>
<use href="#ok"/>
</svg>"""


def test_svg_sanitizer_drops_scripts_handlers_and_external_references() -> None:
    out = sanitize_svg(EVIL_SVG).decode()
    for bad in (
        "script",
        "foreignObject",
        "onload",
        "onclick",
        "evil.example",
        "file:",
        "javascript",
    ):
        assert bad not in out, bad
    assert "data:image/png;base64,AAAA" in out and 'href="#ok"' in out and "<rect" in out


HOSTILE_SVGS = {
    "animate_href": b'<svg xmlns="http://www.w3.org/2000/svg"><a><animate attributeName="href" values="javascript:alert(1)"/><rect width="1" height="1"/></a></svg>',
    "set_href": b'<svg xmlns="http://www.w3.org/2000/svg"><a href="#x"><set attributeName="href" to="javascript:alert(1)"/></a></svg>',
    "prefixed_script": b'<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:script>alert(1)</s:script><s:rect width="1" height="1"/></s:svg>',
    "uppercase_handler": b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1" OnClick="alert(1)" ONMOUSEOVER="x()"/></svg>',
    "xlink_javascript": b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><a xlink:href="javascript:alert(1)"><rect width="1" height="1"/></a></svg>',
    "css_import_attr": b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import "http://evil.example/x.css";</style><rect width="1" height="1" style="background:url(//evil.example/x)"/></svg>',
    "iframe_object_embed": b'<svg xmlns="http://www.w3.org/2000/svg"><iframe src="http://evil.example"/><object data="http://evil.example"/><embed src="http://evil.example"/><rect width="1" height="1"/></svg>',
    "nested_foreign": b'<svg xmlns="http://www.w3.org/2000/svg"><g><g><foreignObject><body xmlns="http://www.w3.org/1999/xhtml" onload="x()"/></foreignObject></g></g><rect width="1" height="1"/></svg>',
}


@pytest.mark.parametrize("name", sorted(HOSTILE_SVGS))
def test_hostile_svgs_are_cleaned(name: str) -> None:
    out = sanitize_svg(HOSTILE_SVGS[name]).decode().lower()
    for bad in ("javascript", "evil.example", "script", "foreignobject", "onclick", "onload"):
        assert bad not in out, (name, bad)
    for tag in ("<iframe", "<object", "<embed", "<animate", "<set", "onmouseover", "@import"):
        assert tag not in out, (name, tag)


def test_svg_with_a_doctype_or_entities_is_refused() -> None:
    bomb = b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>'
    with pytest.raises(DomainError):
        sanitize_svg(bomb)
    with pytest.raises(DomainError):
        sanitize_svg(b"<html></html>")


def test_inspect_sniffs_the_real_type() -> None:
    assert inspect(png())[:3] == ("image/png", 60, 40)
    assert inspect(SVG)[:3] == ("image/svg+xml", 20, 10)
    with pytest.raises(DomainError):
        inspect(b"GIF89a not really")
    with pytest.raises(DomainError):
        inspect(b"x" * (5 * 1024 * 1024 + 1))


# ---- endpoints -------------------------------------------------------------------------------


async def graduate(admin: httpx.AsyncClient, **kw: Any) -> tuple[dict[str, Any], str]:
    cohort, ids = await finished_cohort(admin, {"Каримов Али": (40, 35)}, **kw)
    eid = ids["Каримов Али"]
    await sql(
        "UPDATE student SET gender = 'male' WHERE id = (SELECT student_id FROM enrollment WHERE id = :i)",
        i=eid,
    )
    return cohort, eid


async def certify(admin: httpx.AsyncClient, eid: str) -> str:
    r = await admin.post(f"{G}/{eid}/certificate")
    assert r.status_code == 200, r.text
    return str(r.json()["certificate_no"])


async def test_pdf_happy_path_audit_and_file_name(admin: httpx.AsyncClient) -> None:
    await make_template()
    _, eid = await graduate(admin)
    number = await certify(admin, eid)
    r = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="{number}_karimov_ali.pdf"'
    text = pdf_text(r.content)
    assert "Каримов Али" in text and number in text and "Веб" not in text or number in text
    log = (await admin.get("/api/v1/audit", params={"action": "enrollment.certificate_pdf"})).json()
    assert log["total"] == 1 and "скачан сертификат" in log["items"][0]["text"]
    assert number in log["items"][0]["text"]


async def test_pdf_without_a_number_is_409_and_unknown_is_404(admin: httpx.AsyncClient) -> None:
    await make_template()
    _, eid = await graduate(admin)
    r = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert (r.status_code, r.json()["code"]) == (409, "cert_not_issued")
    r = await admin.get(f"{G}/00000000-0000-0000-0000-000000000001/certificate/pdf")
    assert r.status_code == 404
    assert (
        await sql("SELECT count(*) FROM audit_log WHERE action = 'enrollment.certificate_pdf'")
    )[0][0] == 0


async def test_pdf_without_a_template_is_409(admin: httpx.AsyncClient) -> None:
    _, eid = await graduate(admin)
    await certify(admin, eid)
    r = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert (r.status_code, r.json()["code"]) == (409, "cert_no_template")


async def test_pdf_with_a_missing_gender_is_409(admin: httpx.AsyncClient) -> None:
    await make_template(lay=with_layers(text_layer("g", {"gender": {"male": "а", "female": "б"}})))
    _, eid = await graduate(admin)
    await sql("UPDATE student SET gender = NULL")
    await certify(admin, eid)
    r = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert (r.status_code, r.json()["code"]) == (409, "cert_gender_missing")


async def test_pdf_rights_and_branch_scope(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    await make_template()
    _, eid = await graduate(admin)
    await certify(admin, eid)
    nobody = await login_as("nobody", await make_role("Без выпускников", {"dashboard": "view"}))
    assert (await nobody.get(f"{G}/{eid}/certificate/pdf")).status_code == 403
    tpl_only = await login_as("tpl", await make_role("Шаблоны", {"cert_templates": "view"}))
    assert (await tpl_only.get(f"{G}/{eid}/certificate/pdf")).status_code == 403
    other = await login_as(
        "ist", await make_role("Ист", {"graduates": "view"}), branch="Истаравшан"
    )
    assert (await other.get(f"{G}/{eid}/certificate/pdf")).status_code == 404
    own = await login_as("dsh", await make_role("Душ", {"graduates": "view"}), branch="Душанбе")
    assert (await own.get(f"{G}/{eid}/certificate/pdf")).status_code == 200
    ins = await login_as("ins", "instructor", branch="Душанбе")
    assert (await ins.get(f"{G}/{eid}/certificate/pdf")).status_code == 403


async def test_template_comes_from_the_query_then_the_course_rule_then_the_default(
    admin: httpx.AsyncClient,
) -> None:
    await make_template()
    ruled = await make_template("special_ru", with_layers(text_layer("s", {"text": "СПЕЦИАЛЬНЫЙ"})))
    explicit = await make_template("pick_ru", with_layers(text_layer("p", {"text": "ВЫБРАННЫЙ"})))
    cohort, eid = await graduate(admin)
    await certify(admin, eid)
    r = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert "СПЕЦИАЛЬНЫЙ" not in pdf_text(r.content)
    await sql(
        "INSERT INTO cert_template_rule (course_id, template_id) VALUES (:c, :t)",
        c=cohort["course_id"], t=ruled,
    )  # fmt: skip
    # an issued certificate keeps its template when the rules change later
    assert "СПЕЦИАЛЬНЫЙ" not in pdf_text((await admin.get(f"{G}/{eid}/certificate/pdf")).content)
    await sql("UPDATE enrollment SET certificate_version_id = NULL")
    assert "СПЕЦИАЛЬНЫЙ" in pdf_text((await admin.get(f"{G}/{eid}/certificate/pdf")).content)
    r = await admin.get(f"{G}/{eid}/certificate/pdf", params={"template_id": explicit})
    assert "ВЫБРАННЫЙ" in pdf_text(r.content)
    r = await admin.get(
        f"{G}/{eid}/certificate/pdf", params={"template_id": "00000000-0000-0000-0000-000000000001"}
    )
    assert r.status_code == 404


async def test_the_latest_published_version_is_used(admin: httpx.AsyncClient) -> None:
    tid = await make_template(lay=with_layers(text_layer("a", {"text": "ПЕРВАЯ"})))
    new = with_layers(text_layer("a", {"text": "ВТОРАЯ"}))
    await sql(
        "INSERT INTO cert_template_version (template_id, version_no, layout) VALUES (:t, 2, CAST(:l AS jsonb))",
        t=tid, l=json.dumps(new),
    )  # fmt: skip
    _, eid = await graduate(admin)
    await certify(admin, eid)
    assert "ВТОРАЯ" in pdf_text((await admin.get(f"{G}/{eid}/certificate/pdf")).content)
    with pytest.raises(Exception, match="never updated"):
        await sql("UPDATE cert_template_version SET version_no = 9")


async def test_issued_certificate_keeps_its_version_and_new_ones_get_the_new_icon(
    admin: httpx.AsyncClient,
) -> None:
    old_icon = await admin.post(
        "/api/v1/cert-assets",
        files={"file": ("a.svg", SVG, "image/svg+xml")},
        data={"kind": "image"},
    )
    new_svg = SVG.replace(b"#eee", b"#c00")
    new_icon = await admin.post(
        "/api/v1/cert-assets",
        files={"file": ("b.svg", new_svg, "image/svg+xml")},
        data={"kind": "image"},
    )
    icon = {
        "id": "donor",
        "type": "image",
        "x_mm": 20,
        "y_mm": 20,
        "w_mm": 40,
        "h_mm": 20,
        "source": {"asset": old_icon.json()["id"]},
    }
    tid = await make_template(lay=with_layers(text_layer("a", {"text": "ПЕРВАЯ"}), icon))
    cohort, ids = await finished_cohort(admin, {"Каримов Али": (40, 35), "Рахимов Тимур": (40, 35)})
    for eid in ids.values():
        await sql(
            "UPDATE student SET gender = 'male' WHERE id = (SELECT student_id FROM enrollment WHERE id = :i)",
            i=eid,
        )
    first, second = ids["Каримов Али"], ids["Рахимов Тимур"]
    await certify(admin, first)
    before = await admin.get(f"{G}/{first}/certificate/pdf")
    # the owner replaces the icon and publishes version 2
    v2 = with_layers(
        text_layer("a", {"text": "ВТОРАЯ"}), {**icon, "source": {"asset": new_icon.json()["id"]}}
    )
    await sql(
        "INSERT INTO cert_template_version (template_id, version_no, layout) VALUES (:t, 2, CAST(:l AS jsonb))",
        t=tid, l=json.dumps(v2),
    )  # fmt: skip
    after = await admin.get(f"{G}/{first}/certificate/pdf")
    explicit = await admin.get(f"{G}/{first}/certificate/pdf", params={"template_id": tid})
    for r in (before, after, explicit):
        assert r.status_code == 200, r.text
        assert "ПЕРВАЯ" in pdf_text(r.content) and "ВТОРАЯ" not in pdf_text(r.content)
    assert pdf_streams(after.content) == pdf_streams(before.content)
    await certify(admin, second)
    fresh = await admin.get(f"{G}/{second}/certificate/pdf")
    assert "ВТОРАЯ" in pdf_text(fresh.content)
    assert RED in pdf_streams(fresh.content) and RED not in pdf_streams(before.content)
    assert RED not in pdf_streams(after.content)
    pinned = await sql(
        "SELECT e.id, v.version_no FROM enrollment e JOIN cert_template_version v ON v.id = e.certificate_version_id"
    )
    assert {str(r[0]): r[1] for r in pinned} == {first: 1, second: 2}
    # the template list names the pinned template as the default
    listed = (await admin.get(f"{G}/{first}/certificate/templates")).json()
    assert listed["default_template_id"] == tid


async def test_templates_list_and_preview(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    tid = await make_template()
    r = await admin.get("/api/v1/cert-templates")
    assert r.status_code == 200
    (item,) = r.json()["items"]
    assert (item["key"], item["latest_version_no"], item["status"]) == (GENERAL, 1, "active")
    for sample, name in (
        ("short", "Каримов Али"),
        ("long", "Абдурахмонзода"),
        ("female", "Раҳимова"),
    ):
        p = await admin.post(f"/api/v1/cert-templates/{tid}/preview", params={"sample": sample})
        assert p.status_code == 200 and p.headers["content-type"] == "application/pdf"
        assert name in pdf_text(p.content)
    assert (
        await admin.post(f"/api/v1/cert-templates/{tid}/preview", params={"sample": "x"})
    ).status_code == 422
    assert (await sql("SELECT count(*) FROM audit_log WHERE action LIKE '%certificate%'"))[0][
        0
    ] == 0
    grads = await login_as("g", await make_role("Вып", {"graduates": "change"}))
    assert (await grads.get("/api/v1/cert-templates")).status_code == 403
    assert (await grads.post(f"/api/v1/cert-templates/{tid}/preview")).status_code == 403
    viewer = await login_as("v", await make_role("Шабл", {"cert_templates": "view"}))
    assert (await viewer.get("/api/v1/cert-templates")).status_code == 200
    assert (await viewer.post(f"/api/v1/cert-templates/{tid}/preview")).status_code == 200


async def test_cert_templates_is_a_superadmin_section_by_default() -> None:
    rows = await sql("SELECT count(*) FROM role_permission WHERE section = 'cert_templates'")
    assert rows[0][0] == 0


# ---- import ----------------------------------------------------------------------------------


def write_seed(tmp: Path, lay: dict[str, Any] | None = None) -> Path:
    d = tmp / "seed"
    d.mkdir()
    (d / "bg.png").write_bytes(png())
    (d / "general_ru.json").write_text(json.dumps(lay or layout("bg.png")))
    (d / "templates.json").write_text(
        json.dumps(
            [{"key": "general_ru", "name": "General RU", "lang": "ru", "layout": "general_ru.json"}]
        )
    )
    return d


async def counts() -> tuple[int, int, int]:
    return (
        (await sql("SELECT count(*) FROM cert_asset"))[0][0],
        (await sql("SELECT count(*) FROM cert_template"))[0][0],
        (await sql("SELECT count(*) FROM cert_template_version"))[0][0],
    )


async def run_import(layouts: Path, images: Path | None = None) -> Any:
    async with sessionmaker() as db:
        c = await import_templates(db, layouts, images or layouts)
        await db.commit()
        return c


async def test_import_is_idempotent_and_publishes_only_changes(tmp_path: Path) -> None:
    d = write_seed(tmp_path)
    first = await run_import(d)
    assert (first.assets_created, first.templates_created, first.versions_published) == (1, 1, 1)
    assert await counts() == (1, 1, 1)
    again = await run_import(d)
    assert (again.assets_created, again.templates_created, again.versions_published) == (0, 0, 0)
    assert await counts() == (1, 1, 1)
    # the draft holds the asset id, not the file name
    (draft,) = await sql("SELECT draft->'background'->>'asset' FROM cert_template")
    assert draft[0] != "bg.png" and len(draft[0]) == 36
    changed = layout("bg.png")
    changed["layers"][1]["content"][0]["text"] = "завершил курс «"
    (d / "general_ru.json").write_text(json.dumps(changed))
    third = await run_import(d)
    assert (third.templates_updated, third.versions_published) == (1, 1)
    assert await counts() == (1, 1, 2)
    assert (await sql("SELECT max(version_no) FROM cert_template_version"))[0][0] == 2
    log = (await sql("SELECT count(*) FROM audit_log WHERE action = 'cert_template.publish'"))[0][0]
    assert log == 2


async def test_import_with_separate_image_dir_and_a_shared_image(tmp_path: Path) -> None:
    d = write_seed(tmp_path)
    images = tmp_path / "imgs"
    images.mkdir()
    (images / "bg.png").write_bytes((d / "bg.png").read_bytes())
    (d / "bg.png").unlink()
    c = await run_import(d, images)
    assert c.assets_created == 1
    # the same bytes under another name are one asset
    (images / "other.png").write_bytes(png())
    lay = layout("other.png")
    (d / "second.json").write_text(json.dumps(lay))
    manifest = json.loads((d / "templates.json").read_text())
    manifest.append({"key": "second_ru", "name": "Second", "layout": "second.json"})
    (d / "templates.json").write_text(json.dumps(manifest))
    c = await run_import(d, images)
    assert (c.assets_created, c.templates_created) == (0, 1)
    assert (await counts())[0] == 1


async def test_import_nested_asset_paths_keep_svg_styles(tmp_path: Path) -> None:
    d = write_seed(tmp_path)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><style>.a{fill:#1a9eda}'
        '</style></defs><rect class="a" width="10" height="10"/></svg>'
    )
    for name in ("one", "two"):
        (d / "parts" / name).mkdir(parents=True)
        (d / "parts" / name / "p.svg").write_text(svg)
    lay = layout("bg.png")
    for n, name in enumerate(("one", "two")):
        lay["layers"].append(
            {
                "id": f"part{n}", "type": "image", "x_mm": 1, "y_mm": 1, "w_mm": 10, "h_mm": 10,
                "rotation": 0, "locked": False, "fit": "contain",
                "source": {"asset": f"parts/{name}/p.svg"},
            }
        )  # fmt: skip
    (d / "general_ru.json").write_text(json.dumps(lay))
    c = await run_import(d)
    assert c.assets_created == 2  # the background and one shared svg
    (row,) = await sql(
        "SELECT mime, convert_from(data, 'UTF8') FROM cert_asset WHERE mime LIKE '%svg%'"
    )
    assert row[0] == "image/svg+xml" and ".a{fill:#1a9eda}" in row[1].replace(" ", "").replace(
        "\n", ""
    )
    lay["layers"][-1]["source"]["asset"] = "parts/../../escape.svg"
    (d / "general_ru.json").write_text(json.dumps(lay))
    with pytest.raises(ImportProblem, match="image not found"):
        await run_import(d)


async def test_import_refuses_missing_images_bad_layouts_and_paths(tmp_path: Path) -> None:
    d = write_seed(tmp_path)
    (d / "bg.png").unlink()
    with pytest.raises(ImportProblem, match="image not found"):
        await run_import(d)
    (tmp_path / "x").mkdir()
    d2 = write_seed(tmp_path / "x")
    bad = layout("bg.png")
    bad["layers"][0]["content"].append({"field": "nope.field"})
    (d2 / "general_ru.json").write_text(json.dumps(bad))
    with pytest.raises(ImportProblem, match="cert_field_unknown"):
        await run_import(d2)
    (d2 / "general_ru.json").write_text(json.dumps(layout("../../etc/passwd")))
    with pytest.raises(ImportProblem, match="image not found"):
        await run_import(d2)
    assert await counts() == (0, 0, 0)


async def test_an_imported_template_renders_through_the_endpoint(
    admin: httpx.AsyncClient, tmp_path: Path
) -> None:
    await run_import(write_seed(tmp_path))
    _, eid = await graduate(admin)
    number = await certify(admin, eid)
    r = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert r.status_code == 200 and number in pdf_text(r.content)


def test_import_cli_arguments() -> None:
    from app.cli import main

    with pytest.raises(SystemExit):
        main(["import-cert-templates", "--bogus"])


def test_layout_dump_roundtrips() -> None:
    data = seed_like()
    assert parse_layout(parse_layout(deepcopy(data)).dump()).dump() == parse_layout(data).dump()


SEED = Path(__file__).parents[1] / "app" / "certificates" / "seed"
SEED_FILES = sorted(p for p in SEED.glob("*.json") if p.name != "templates.json")


def test_there_are_ten_seed_layouts_and_the_manifest_names_them() -> None:
    manifest = json.loads((SEED / "templates.json").read_text())
    assert len(SEED_FILES) == 10
    assert {m["layout"] for m in manifest} == {p.name for p in SEED_FILES}


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.stem)
@pytest.mark.parametrize("sample", ["short", "long", "female"])
def test_every_seed_layout_renders_with_sample_data(path: Path, sample: str) -> None:
    lay = parse_layout(json.loads(path.read_text()))
    pw, ph = lay.page.width_mm, lay.page.height_mm
    blank = png(size=(max(1, round(pw)), max(1, round(ph))))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pw:g} {ph:g}"/>'.encode()
    assets = {
        ref: ("image/svg+xml", svg) if ref.endswith(".svg") else ("image/png", blank)
        for ref in lay.asset_refs()
    }
    pdf = render.render_sync(lay, sample_context(sample), assets)
    box = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
    assert float(box.width) == pytest.approx(pw * MM, abs=0.5)
    assert float(box.height) == pytest.approx(ph * MM, abs=0.5)


async def test_pdf_uses_the_director_of_the_template_language(admin: httpx.AsyncClient) -> None:
    lay = with_layers(
        text_layer("n", {"field": "company.director_name"}),
        text_layer("t", {"field": "company.director_title"}),
    )
    await make_template(lay=lay)
    en = await make_template("english_en", lay, lang="en")
    _, eid = await graduate(admin)
    await certify(admin, eid)
    ru_text = pdf_text((await admin.get(f"{G}/{eid}/certificate/pdf")).content)
    assert "Озодамо Фаромуз" in ru_text
    en_text = pdf_text(
        (await admin.get(f"{G}/{eid}/certificate/pdf", params={"template_id": en})).content
    )
    assert "Ozodamo Faromuz" in en_text and "CEO Ilmhona" in en_text


async def test_certificate_templates_list(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    ru = await make_template()
    en = await make_template("english_en", lang="en")
    await make_template("draft_only_ru")
    await sql(
        "DELETE FROM cert_template_version "
        "WHERE template_id = (SELECT id FROM cert_template WHERE key = 'draft_only_ru')"
    )
    _, eid = await graduate(admin)
    url = f"{G}/{eid}/certificate/templates"
    r = await admin.get(url)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_template_id"] == ru
    assert {(t["id"], t["lang"]) for t in body["templates"]} == {(ru, "ru"), (en, "en")}
    gone = f"{G}/00000000-0000-0000-0000-000000000001/certificate/templates"
    assert (await admin.get(gone)).status_code == 404
    nobody = await login_as("nobody", await make_role("Без выпускников", {"dashboard": "view"}))
    assert (await nobody.get(url)).status_code == 403
    tpl_only = await login_as("tpl", await make_role("Шаблоны", {"cert_templates": "view"}))
    assert (await tpl_only.get(url)).status_code == 403
    other = await login_as(
        "ist", await make_role("Ист", {"graduates": "view"}), branch="Истаравшан"
    )
    assert (await other.get(url)).status_code == 404
    own = await login_as("dsh", await make_role("Душ", {"graduates": "view"}), branch="Душанбе")
    assert (await own.get(url)).status_code == 200
