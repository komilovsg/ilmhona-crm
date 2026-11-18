"""Certificates C1b: the company director (settings, signature and seal images), the photo
cleaner, the `rect` layer and the director fields."""

import io
import json
import random
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from pypdf import PdfReader

from app.audit.sentences import Entry, sentence
from app.certificates import render
from app.certificates.fields import apply_settings, load_settings, sample_context
from app.certificates.importer import ImportProblem, import_settings
from app.certificates.layout import parse_layout
from app.certificates.signature import clean
from app.core.db import sessionmaker
from app.core.errors import DomainError
from tests.certs import layout, png, text_layer
from tests.conftest import SignedIn, make_role, sql

URL = "/api/v1/cert-settings"
INK = (20, 30, 120)


def pdf_text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def photo(size: tuple[int, int] = (900, 500), seed: int = 1) -> bytes:
    """A synthetic phone photo: grey gradient paper, dark pen strokes, noise."""
    rng = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    assert px is not None
    for y in range(h):
        for x in range(w):
            base = 235 - 55 * x / w - 20 * y / h  # uneven light: 235 .. 160
            n = rng.randint(-5, 5)
            px[x, y] = (int(base) + n, int(base) + n, int(base) + n)
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    d.line([(200, 300), (300, 150), (400, 330), (520, 170), (700, 300)], fill=INK, width=9)
    d.ellipse((330, 200, 420, 280), outline=INK, width=7)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def transparent_png() -> bytes:
    img = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    for x in range(40, 260):
        for y in (50, 51, 52, 53):
            img.putpixel((x, y), (200, 20, 20, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def files(data: bytes, name: str = "s.png", mime: str = "image/png") -> dict[str, Any]:
    return {"file": (name, data, mime)}


# ---- the cleaner ----------------------------------------------------------------------------


def test_a_photo_loses_its_paper_and_keeps_the_ink() -> None:
    out = Image.open(io.BytesIO(clean(photo()))).convert("RGBA")
    assert out.width <= 1200 and out.mode == "RGBA"
    alphas = list(out.getchannel("A").tobytes())
    opaque = sum(1 for a in alphas if a > 200)
    clear = sum(1 for a in alphas if a < 10)
    assert opaque > 500  # the strokes stay
    assert clear / len(alphas) > 0.85  # the paper, bright or dim, is gone
    # cropped to the strokes with a small margin: the paper area around them is not kept
    assert out.width < 700 and out.height < 300
    raw = out.tobytes()
    pixels = [raw[i : i + 4] for i in range(0, len(raw), 4)]
    r, g, b, _ = max(pixels, key=lambda q: q[3])
    assert (r, g, b) != (0, 0, 0) and b > r  # the pen is blue, the colour survives


def test_ink_options_and_downscale() -> None:
    blue = Image.open(io.BytesIO(clean(photo(), "blue"))).convert("RGBA")
    black = Image.open(io.BytesIO(clean(photo(), "black"))).convert("RGBA")
    assert blue.getpixel((blue.width // 2, blue.height // 2))[:3] == (16, 38, 120)
    assert black.getpixel((0, 0))[:3] == (0, 0, 0)
    big = Image.open(io.BytesIO(clean(photo((2400, 1000))))).convert("RGBA")
    assert big.width <= 1200


def test_a_transparent_png_keeps_its_transparency() -> None:
    out = Image.open(io.BytesIO(clean(transparent_png()))).convert("RGBA")
    assert out.getpixel((out.width // 2, out.height // 2))[3] == 255
    assert out.getpixel((out.width // 2, out.height // 2))[:3] == (200, 20, 20)
    assert out.getpixel((0, 0))[3] == 0
    assert out.width < 300  # cropped


@pytest.mark.parametrize(
    "data",
    [b"hello", b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"\x89PNG\r\n\x1a\nbroken"],
)
def test_the_cleaner_refuses_what_is_not_a_png_or_jpeg(data: bytes) -> None:
    with pytest.raises(DomainError) as exc:
        clean(data)
    assert exc.value.error.code == "cert_asset_invalid"


def test_the_cleaner_refuses_blank_paper_big_input_and_a_gif() -> None:
    blank = io.BytesIO()
    Image.new("RGB", (400, 300), (240, 240, 240)).save(blank, format="PNG")
    with pytest.raises(DomainError):
        clean(blank.getvalue())
    with pytest.raises(DomainError):
        clean(b"0" * (8 * 1024 * 1024 + 1))
    gif = io.BytesIO()
    Image.new("RGB", (40, 30)).save(gif, format="GIF")
    with pytest.raises(DomainError):
        clean(gif.getvalue())


# ---- settings endpoints ----------------------------------------------------------------------


async def test_settings_default_and_rights(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    r = await admin.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert (body["director_name"], body["director_title"]) == (
        "Озодамо Фаромуз",
        "Директор ОО Илмхона",
    )
    assert body["signature_asset_id"] is None and body["seal_asset_id"] is None
    nobody = await login_as("n", await make_role("Без", {"graduates": "change"}))
    assert (await nobody.get(URL)).status_code == 403
    assert (
        await nobody.patch(URL, json={"director_name": "X"}, no_version=True)
    ).status_code == 403
    viewer = await login_as("v", await make_role("Смотрит", {"cert_templates": "view"}))
    assert (await viewer.get(URL)).status_code == 200
    assert (await viewer.patch(URL, json={"director_name": "X"})).status_code == 403
    assert (await viewer.post(f"{URL}/signature", files=files(photo()))).status_code == 403
    assert (await viewer.delete(f"{URL}/seal")).status_code == 403
    manager = await login_as("m", await make_role("Меняет", {"cert_templates": "change"}))
    assert (await manager.patch(URL, json={"director_name": "Тестов Тест"})).status_code == 200


async def test_patch_updates_audits_and_reads_in_russian(admin: httpx.AsyncClient) -> None:
    r = await admin.patch(URL, json={"director_name": "  Тестов Тест  "})
    assert r.status_code == 200 and r.json()["director_name"] == "Тестов Тест"
    assert r.json()["director_title"] == "Директор ОО Илмхона"  # not sent, not touched
    (row,) = await sql(
        "SELECT action, entity, diff, label FROM audit_log WHERE entity = 'cert_settings'"
    )
    assert row[0] == "cert_settings.update"
    assert row[2]["director_name"] == ["Озодамо Фаромуз", "Тестов Тест"]
    text = sentence(Entry("Админ", row[0], row[1], row[3], row[2]))
    assert text == "Админ: изменены настройки сертификатов: директор Озодамо Фаромуз → Тестов Тест"
    # nothing changed: no new audit entry
    await admin.patch(URL, json={"director_name": "Тестов Тест"})
    assert (await sql("SELECT count(*) FROM audit_log WHERE entity = 'cert_settings'"))[0][0] == 1
    assert (await admin.patch(URL, json={"director_title": ""})).status_code == 422
    assert (await admin.patch(URL, json={"nope": 1})).status_code == 422


async def test_patch_with_a_stale_version_is_409(admin: httpx.AsyncClient) -> None:
    await admin.patch(URL, json={"director_name": "Первый"})
    r = await admin.patch(URL, json={"director_name": "Второй"}, headers={"X-Record-Version": "1"})
    assert r.status_code == 409
    assert (await admin.get(URL)).json()["director_name"] == "Первый"
    assert (await admin.patch(URL, json={"director_name": "Х"}, no_version=True)).status_code == 428


async def test_upload_cleans_stores_audits_and_deletes(admin: httpx.AsyncClient) -> None:
    r = await admin.post(f"{URL}/signature", files=files(photo(), "p.jpg", "image/jpeg"))
    assert r.status_code == 200, r.text
    sid = r.json()["signature_asset_id"]
    assert sid
    got = await admin.get(f"{URL}/signature")
    assert got.headers["content-type"] == "image/png"
    out = Image.open(io.BytesIO(got.content))
    assert out.mode == "RGBA" and out.width <= 1200
    kind = (await sql("SELECT kind, mime FROM cert_asset WHERE id = :i", i=sid))[0]
    assert tuple(kind) == ("signature", "image/png")
    seal = await admin.post(f"{URL}/seal", files=files(transparent_png()), params={"ink": "black"})
    assert seal.status_code == 200 and seal.json()["seal_asset_id"]
    assert (await admin.get(f"{URL}/seal")).status_code == 200
    actions = [
        a[0]
        for a in await sql(
            "SELECT action FROM audit_log WHERE entity = 'cert_settings' ORDER BY at"
        )
    ]
    assert actions == ["cert_settings.signature_upload", "cert_settings.seal_upload"]
    d = await admin.delete(f"{URL}/signature")
    assert d.status_code == 200 and d.json()["signature_asset_id"] is None
    assert (await admin.get(f"{URL}/signature")).status_code == 404
    await admin.delete(f"{URL}/signature")  # again: nothing to remove, no audit entry
    assert (
        await sql("SELECT count(*) FROM audit_log WHERE action = 'cert_settings.signature_delete'")
    )[0][0] == 1
    entry = (
        await sql(
            "SELECT action, entity, label, diff FROM audit_log WHERE action = 'cert_settings.seal_upload'"
        )
    )[0]
    assert sentence(Entry("А", *entry)) == "А: загружена печать для сертификатов"


async def test_upload_validation_and_preview_saves_nothing(admin: httpx.AsyncClient) -> None:
    svg = b"<svg xmlns='http://www.w3.org/2000/svg' width='9' height='9'><rect width='9' height='9'/></svg>"
    for bad in (b"just text", svg, b"0" * (8 * 1024 * 1024 + 1)):
        r = await admin.post(f"{URL}/signature", files=files(bad))
        assert r.status_code == 422 and r.json()["code"] == "cert_asset_invalid", bad[:10]
    gif = io.BytesIO()
    Image.new("RGB", (40, 30)).save(gif, format="GIF")
    assert (await admin.post(f"{URL}/signature", files=files(gif.getvalue()))).status_code == 422
    assert (
        await admin.post(f"{URL}/signature", files=files(photo()), params={"ink": "x"})
    ).status_code == 422
    assert (await sql("SELECT count(*) FROM cert_asset"))[0][0] == 0
    p = await admin.post(f"{URL}/signature/preview", files=files(photo()), params={"ink": "blue"})
    assert p.status_code == 200 and p.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(p.content)).mode == "RGBA"
    assert (await sql("SELECT count(*) FROM cert_asset"))[0][0] == 0
    assert (await sql("SELECT count(*) FROM audit_log WHERE entity = 'cert_settings'"))[0][0] == 0


# ---- layout and render ---------------------------------------------------------------------------

BG = {"bg": ("image/png", png())}


def director_layout(*extra: dict[str, Any]) -> dict[str, Any]:
    return layout(
        "bg",
        {"id": "cover", "type": "rect", "x_mm": 10, "y_mm": 150, "w_mm": 60, "h_mm": 30, "fill": "#ffffff"},
        {"id": "seal", "type": "image", "x_mm": 12, "y_mm": 152, "w_mm": 20, "h_mm": 20,
         "source": {"company": "seal"}},
        {"id": "sig", "type": "image", "x_mm": 30, "y_mm": 152, "w_mm": 30, "h_mm": 20,
         "source": {"signature": "director"}},
        text_layer("dname", {"field": "company.director_name"}, size_pt=12),
        text_layer("dtitle", {"field": "company.director_title"}, size_pt=12),
        *extra,
    )  # fmt: skip


def test_rect_layer_schema() -> None:
    lay = parse_layout(director_layout())
    assert lay.schema_ == 1 and lay.dump()["layers"][0]["fill"] == "#ffffff"
    bad = director_layout()
    bad["layers"][0]["fill"] = "white"
    with pytest.raises(DomainError):
        parse_layout(bad)
    extra = director_layout()
    extra["layers"][0]["colour"] = "#000000"
    with pytest.raises(DomainError):
        parse_layout(extra)
    wrong = director_layout()
    wrong["layers"][1]["source"] = {"company": "logo"}
    with pytest.raises(DomainError):
        parse_layout(wrong)


def test_director_fields_render_and_missing_images_draw_nothing() -> None:
    ctx = sample_context("short")
    ctx.values["company.director_name"] = "Тестов Тест"
    ctx.values["company.director_title"] = "Директор ОО Илмхона"
    pdf = render.render_sync(parse_layout(director_layout()), ctx, BG)
    text = pdf_text(pdf)
    assert "Тестов Тест" in text and "Директор ОО Илмхона" in text
    assert pdf.count(b"/Subtype /Image") == 1  # the background only


def test_signature_and_seal_assets_are_drawn_when_set() -> None:
    ctx = sample_context("short")
    ctx.signature_ref, ctx.seal_ref = "sig-id", "seal-id"
    assets = {
        **BG,
        "sig-id": ("image/png", transparent_png()),
        "seal-id": ("image/png", transparent_png()),
    }
    pdf = render.render_sync(parse_layout(director_layout()), ctx, assets)
    assert pdf.count(b"/Subtype /Image") >= 3


async def test_the_preview_uses_the_stored_director(admin: httpx.AsyncClient) -> None:
    from tests.certs import make_template

    tid = await make_template(lay=director_layout())
    await admin.patch(URL, json={"director_name": "Тестов Тест"})
    r = await admin.post(f"/api/v1/cert-templates/{tid}/preview")
    assert r.status_code == 200 and "Тестов Тест" in pdf_text(r.content)
    await admin.post(f"{URL}/seal", files=files(transparent_png()))
    r2 = await admin.post(f"/api/v1/cert-templates/{tid}/preview")
    assert r2.content.count(b"/Subtype /Image") > r.content.count(b"/Subtype /Image")


async def test_settings_row_cannot_be_duplicated() -> None:
    with pytest.raises(Exception, match="cert_settings_single_row"):
        await sql("INSERT INTO cert_settings (id) VALUES (2)")


# ---- import ----------------------------------------------------------------------------------


async def run_settings(images: Path) -> Any:
    from app.certificates.importer import Counts

    counts = Counts()
    async with sessionmaker() as db:
        await import_settings(db, images, counts)
        await db.commit()
    return counts


async def test_settings_import_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "director").mkdir()
    (tmp_path / "director" / "sig.png").write_bytes(transparent_png())
    (tmp_path / "director" / "seal.png").write_bytes(transparent_png())
    assert (await run_settings(tmp_path)).settings_changed == 0  # no settings.json: nothing
    (tmp_path / "settings.json").write_text(
        json.dumps({
            "director_name": "Импортов Имя",
            "director_title": "Директор",
            "signature": "director/sig.png",
            "seal": "director/seal.png",
        })
    )  # fmt: skip
    first = await run_settings(tmp_path)
    assert first.settings_changed == 1
    async with sessionmaker() as db:
        row = await load_settings(db)
        assert (row.director_name, row.director_title) == ("Импортов Имя", "Директор")
        assert row.director_signature_asset_id and row.seal_asset_id
        ctx = apply_settings(sample_context("short"), row)
        assert ctx.values["company.director_name"] == "Импортов Имя" and ctx.signature_ref
    assert (await sql("SELECT count(*) FROM cert_asset"))[0][0] == 1  # same bytes stored once
    version = (await sql("SELECT version FROM cert_settings"))[0][0]
    again = await run_settings(tmp_path)
    assert again.settings_changed == 0 and again.assets_created == 0
    assert (await sql("SELECT version FROM cert_settings"))[0][0] == version
    assert (await sql("SELECT count(*) FROM audit_log WHERE entity = 'cert_settings'"))[0][0] == 1


async def test_settings_import_keeps_a_director_set_in_the_crm(admin: Any, tmp_path: Path) -> None:
    await sql("UPDATE cert_settings SET updated_by = (SELECT id FROM app_user LIMIT 1)")
    (tmp_path / "settings.json").write_text(json.dumps({"director_name": "Импортов Имя"}))
    assert (await run_settings(tmp_path)).settings_changed == 0
    assert (await sql("SELECT director_name FROM cert_settings"))[0][0] != "Импортов Имя"


async def test_settings_import_refuses_bad_files(tmp_path: Path) -> None:
    (tmp_path / "settings.json").write_text(json.dumps({"director_name": "А", "boss": 1}))
    with pytest.raises(ImportProblem):
        await run_settings(tmp_path)
    (tmp_path / "settings.json").write_text(json.dumps({"signature": "../x.png"}))
    with pytest.raises(ImportProblem):
        await run_settings(tmp_path)


SEED = Path(__file__).parents[1] / "app" / "certificates" / "seed"


def test_covered_seed_layouts_draw_the_director_over_a_cover() -> None:
    covered = {
        p.stem: [layer["id"] for layer in json.loads(p.read_text())["layers"]]
        for p in SEED.glob("*.json")
        if p.name != "templates.json" and "dir_cover" in p.read_text()
    }
    assert set(covered) == {"proskills", "proskills_islom", "proskills_umed", "itp", "kids_scratch"}
    for ids in covered.values():
        assert ids[:5] == ["dir_cover", "dir_seal", "dir_signature", "dir_name", "dir_title"]
