"""Certificates C4: the template editor API (create, draft, publish, restore, draft preview,
images, field catalog, fonts, rules)."""

import io
from copy import deepcopy
from typing import Any

import httpx
from PIL import Image
from pypdf import PdfReader

from tests.certs import SVG, layout, make_template, png, text_layer
from tests.conftest import SignedIn, make_role, make_user, sql
from tests.edu import make_course

T = "/api/v1/cert-templates"


def pdf_text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def upload(data: bytes, name: str = "a.png", mime: str = "image/png") -> dict[str, Any]:
    return {"file": (name, data, mime)}


async def asset(
    admin: httpx.AsyncClient, kind: str = "background", data: bytes | None = None
) -> str:
    r = await admin.post("/api/v1/cert-assets", files=upload(data or png()), data={"kind": kind})
    assert r.status_code == 200, r.text
    return str(r.json()["id"])


async def new(admin: httpx.AsyncClient, name: str = "Новый") -> dict[str, Any]:
    r = await admin.post(T, json={"name": name})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def with_bg(lay: dict[str, Any], ref: str) -> dict[str, Any]:
    out = deepcopy(lay)
    out["background"] = {"asset": ref}
    return out


async def log_texts(admin: httpx.AsyncClient) -> list[str]:
    r = await admin.get("/api/v1/audit", params={"per_page": 100})
    return [i["text"] for i in r.json()["items"]]


async def test_rights_matrix(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    t = await new(admin)
    tid = t["id"]
    none = await login_as("n", await make_role("Без", {"graduates": "change"}))
    for call in (
        none.get(T),
        none.get(f"{T}/{tid}"),
        none.get("/api/v1/cert-fields"),
        none.get("/api/v1/cert-template-rules"),
        none.get("/api/v1/cert-fonts/Montserrat-400.ttf"),
        none.post(T, json={"name": "X"}),
        none.patch(f"{T}/{tid}", json={"name": "X"}, no_version=True),
        none.post(f"{T}/{tid}/publish"),
        none.post(f"{T}/{tid}/draft-preview", json={"layout": t["draft"]}),
        none.post("/api/v1/cert-assets", files=upload(png()), data={"kind": "image"}),
        none.put("/api/v1/cert-template-rules", json={"rules": []}, no_version=True),
    ):
        assert (await call).status_code == 403
    view = await login_as("v", await make_role("Смотрит", {"cert_templates": "view"}))
    assert (await view.get(T)).status_code == 200
    assert (await view.get(f"{T}/{tid}")).status_code == 200
    assert (await view.get("/api/v1/cert-fields")).status_code == 200
    assert (await view.get("/api/v1/cert-template-rules")).status_code == 200
    assert (await view.patch(f"{T}/{tid}", json={"name": "X"})).status_code == 403
    assert (await view.post(T, json={"name": "X"})).status_code == 403
    assert (await view.post(f"{T}/{tid}/publish")).status_code == 403
    assert (
        await view.post(f"{T}/{tid}/draft-preview", json={"layout": t["draft"]})
    ).status_code == 403
    assert (
        await view.post("/api/v1/cert-assets", files=upload(png()), data={"kind": "image"})
    ).status_code == 403
    assert (
        await view.put("/api/v1/cert-template-rules", json={"rules": []}, no_version=True)
    ).status_code == 403
    assert (await view.delete(f"{T}/{tid}")).status_code == 405
    change = await login_as("c", await make_role("Меняет", {"cert_templates": "change"}))
    assert (await change.patch(f"{T}/{tid}", json={"name": "Другое"})).status_code == 200


async def test_create_blank_slug_and_name_taken(admin: httpx.AsyncClient) -> None:
    a = await new(admin, "Курс по Python")
    assert a["key"] == "kurs-po-python" and a["status"] == "active" and a["lang"] == "ru"
    assert a["draft"] == {
        "schema": 1,
        "page": {"width_mm": 297, "height_mm": 210},
        "background": None,
        "layers": [],
    }
    assert a["latest_version_no"] is None and a["versions"] == [] and a["rules"] == []
    assert a["has_unpublished_changes"] is True and a["version"] == 1
    b = await new(admin, "Курс по python!")
    assert b["key"] == "kurs-po-python-2"
    r = await admin.post(T, json={"name": "Курс по Python"})
    assert (r.status_code, r.json()["code"]) == (409, "cert_template_name_taken")
    r = await admin.patch(f"{T}/{b['id']}", json={"name": "Курс по Python"})
    assert (r.status_code, r.json()["code"]) == (409, "cert_template_name_taken")


async def test_create_from_a_copy(admin: httpx.AsyncClient) -> None:
    src = await make_template("general_ru")
    r = await admin.post(T, json={"name": "Копия", "from_template_id": src, "lang": "en"})
    assert r.status_code == 201
    body = r.json()
    source = (await admin.get(f"{T}/{src}")).json()
    assert body["draft"] == source["draft"] and body["lang"] == "en"
    assert body["latest_version_no"] is None and body["id"] != src
    miss = await admin.post(
        T, json={"name": "Z", "from_template_id": "00000000-0000-0000-0000-000000000001"}
    )
    assert miss.status_code == 404


async def test_list_items_and_unpublished_flag(admin: httpx.AsyncClient) -> None:
    src = await make_template("general_ru")
    item = (await admin.get(T)).json()["items"][0]
    assert set(item) == {
        "id", "key", "name", "status", "lang", "version", "latest_version_no",
        "updated_at", "has_unpublished_changes",
    }  # fmt: skip
    assert item["latest_version_no"] == 1 and item["has_unpublished_changes"] is False
    draft = (await admin.get(f"{T}/{src}")).json()["draft"]
    draft["layers"].append(
        {"id": "extra", "type": "qr", "x_mm": 1, "y_mm": 1, "w_mm": 20, "h_mm": 20}
    )
    assert (await admin.patch(f"{T}/{src}", json={"draft": draft})).status_code == 200
    assert (await admin.get(T)).json()["items"][0]["has_unpublished_changes"] is True
    one = await new(admin, "Пустой")
    items = {i["name"]: i for i in (await admin.get(T)).json()["items"]}
    assert items["Пустой"]["latest_version_no"] is None
    assert items["Пустой"]["has_unpublished_changes"] is True
    assert one["id"] == items["Пустой"]["id"]


async def test_patch_scalars_status_and_stale_version(admin: httpx.AsyncClient) -> None:
    t = await new(admin)
    r = await admin.patch(f"{T}/{t['id']}", json={"name": "  Иное ", "status": "archived"})
    assert r.status_code == 200
    body = r.json()
    assert (body["name"], body["status"], body["version"]) == ("Иное", "archived", 2)
    assert body["lang"] == "ru"
    stale = await admin.patch(
        f"{T}/{t['id']}", json={"name": "Третье"}, headers={"X-Record-Version": "1"}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    assert (await admin.get(f"{T}/{t['id']}")).json()["name"] == "Иное"
    no = await admin.patch(f"{T}/{t['id']}", json={"name": "Х"}, no_version=True)
    assert no.status_code == 428
    assert (await admin.patch(f"{T}/{t['id']}", json={"nope": 1})).status_code == 422
    assert (await admin.patch(f"{T}/{t['id']}", json={"status": "deleted"})).status_code == 422
    missing = "00000000-0000-0000-0000-000000000001"
    assert (
        await admin.patch(f"{T}/{missing}", json={"name": "A"}, headers={"X-Record-Version": "1"})
    ).status_code == 404


async def test_draft_validation(admin: httpx.AsyncClient) -> None:
    t = await new(admin)
    url = f"{T}/{t['id']}"
    bad = deepcopy(t["draft"])
    bad["page"]["width_mm"] = 5
    bad["layers"].append({"id": "x", "type": "nonsense"})
    r = await admin.patch(url, json={"draft": bad})
    assert (r.status_code, r.json()["code"]) == (422, "cert_layout_invalid")
    assert r.json()["params"]["problems"]
    unknown = deepcopy(t["draft"])
    unknown["layers"].append(text_layer("t", {"field": "student.shoe_size"}))
    r = await admin.patch(url, json={"draft": unknown})
    assert (r.status_code, r.json()["code"]) == (422, "cert_field_unknown")
    ghost = with_bg(t["draft"], "00000000-0000-0000-0000-0000000000aa")
    r = await admin.patch(url, json={"draft": ghost})
    assert (r.status_code, r.json()["code"]) == (422, "cert_asset_missing")
    r = await admin.patch(url, json={"draft": with_bg(t["draft"], "bg.png")})
    assert r.json()["code"] == "cert_asset_missing"
    assert (await admin.get(url)).json()["draft"] == t["draft"]  # nothing was saved


async def test_publish_restore_and_flags(admin: httpx.AsyncClient) -> None:
    t = await new(admin)
    url = f"{T}/{t['id']}"
    ref = await asset(admin)
    d1 = with_bg(layout(None, text_layer("name")), ref)
    saved = (await admin.patch(url, json={"draft": d1})).json()
    assert saved["has_unpublished_changes"] is True and saved["draft"]["layers"][0]["id"] == "name"
    pub = await admin.post(f"{url}/publish")
    assert pub.status_code == 200
    body = pub.json()
    assert body["latest_version_no"] == 1 and body["has_unpublished_changes"] is False
    assert body["versions"][0]["version_no"] == 1 and body["versions"][0]["published_by_name"]
    again = await admin.post(f"{url}/publish")
    assert (again.status_code, again.json()["code"]) == (409, "cert_nothing_to_publish")
    d2 = deepcopy(saved["draft"])
    d2["layers"].append({"id": "qr", "type": "qr", "x_mm": 5, "y_mm": 5, "w_mm": 20, "h_mm": 20})
    flipped = (await admin.patch(url, json={"draft": d2})).json()
    assert flipped["has_unpublished_changes"] is True
    body = (await admin.post(f"{url}/publish")).json()
    assert [v["version_no"] for v in body["versions"]] == [2, 1]
    assert body["latest_version_no"] == 2 and body["has_unpublished_changes"] is False
    version = body["version"]
    stale = await admin.post(f"{url}/restore/1", headers={"X-Record-Version": str(version - 1)})
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    assert (
        await admin.post(f"{url}/restore/1", headers={"X-Record-Version": str(version)})
    ).json()["has_unpublished_changes"] is True
    r = await admin.post(f"{url}/restore/9", headers={"X-Record-Version": str(version + 1)})
    assert r.status_code == 404
    got = (await admin.get(url)).json()
    assert [layer["id"] for layer in got["draft"]["layers"]] == ["name"]
    assert got["latest_version_no"] == 2
    published = await sql(
        "SELECT version_no, layout FROM cert_template_version ORDER BY version_no"
    )
    assert len(published) == 2 and len(published[1][1]["layers"]) == 2  # versions are immutable
    nores = await admin.post(f"{url}/restore/1")
    assert nores.status_code == 428


async def test_draft_preview_renders_unsaved_layout_with_the_director(
    admin: httpx.AsyncClient,
) -> None:
    t = await new(admin)
    url = f"{T}/{t['id']}"
    lay = layout(
        None,
        text_layer("name"),
        text_layer("who", {"field": "company.director_name"}),
    )
    lay["layers"][1]["y_mm"] = 120
    r = await admin.post(f"{url}/draft-preview", json={"layout": lay})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = pdf_text(r.content)
    assert "Каримов Али" in text and "Озодамо Фаромуз" in text
    r = await admin.post(f"{url}/draft-preview", params={"sample": "female"}, json={"layout": lay})
    assert "Раҳимова" in pdf_text(r.content)
    assert (await admin.get(url)).json()["draft"] == t["draft"]  # not saved
    bad = await admin.post(f"{url}/draft-preview", json={"layout": {"schema": 1}})
    assert bad.json()["code"] == "cert_layout_invalid"
    odd = deepcopy(lay)
    odd["layers"].append(text_layer("z", {"field": "no.such"}))
    assert (await admin.post(f"{url}/draft-preview", json={"layout": odd})).json()[
        "code"
    ] == "cert_field_unknown"
    q = await admin.post(f"{url}/draft-preview", params={"sample": "x"}, json={"layout": lay})
    assert q.status_code == 422
    audits = await sql("SELECT count(*) FROM audit_log WHERE entity = 'cert_template'")
    assert audits[0][0] == 1  # only the creation


async def test_asset_upload_kinds_and_limits(admin: httpx.AsyncClient) -> None:
    url = "/api/v1/cert-assets"
    r = await admin.post(url, files=upload(png((1, 2, 3), (60, 40))), data={"kind": "background"})
    assert r.status_code == 200
    body = r.json()
    assert (body["kind"], body["mime"], body["width_px"], body["height_px"]) == (
        "background", "image/png", 60, 40,
    )  # fmt: skip
    assert set(body) == {"id", "kind", "mime", "width_px", "height_px", "size_bytes"}
    again = await admin.post(url, files=upload(png((1, 2, 3), (60, 40))), data={"kind": "image"})
    assert again.json()["id"] == body["id"]  # deduplicated
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (9, 9, 9)).save(buf, format="JPEG")
    jpg = await admin.post(
        url, files=upload(buf.getvalue(), "a.jpg", "image/jpeg"), data={"kind": "image"}
    )
    assert jpg.status_code == 200 and jpg.json()["mime"] == "image/jpeg"
    dirty = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
        b'<script>alert(1)</script><rect width="20" height="10" onload="x()"/></svg>'
    )
    svg = await admin.post(
        url, files=upload(dirty, "a.svg", "image/svg+xml"), data={"kind": "image"}
    )
    assert svg.status_code == 200 and svg.json()["mime"] == "image/svg+xml"
    stored = (await sql("SELECT data FROM cert_asset WHERE id = :i", i=svg.json()["id"]))[0][0]
    assert b"script" not in stored and b"onload" not in stored and b"<rect" in stored
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    for data, name, mime in (
        (gif.getvalue(), "a.gif", "image/gif"),
        (b"not an image at all", "a.png", "image/png"),
        (b"GIF89a" + b"x" * 40, "a.png", "image/png"),
        (b"<html>hi</html>", "a.png", "image/png"),
    ):
        bad = await admin.post(url, files=upload(data, name, mime), data={"kind": "image"})
        assert (bad.status_code, bad.json()["code"]) == (422, "cert_asset_invalid"), name
    big = await admin.post(
        url, files=upload(b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10)), data={"kind": "image"}
    )
    assert (big.status_code, big.json()["code"]) == (422, "cert_asset_invalid")
    wide = io.BytesIO()
    Image.new("1", (8001, 2)).save(wide, format="PNG")
    w = await admin.post(url, files=upload(wide.getvalue()), data={"kind": "image"})
    assert (w.status_code, w.json()["code"]) == (422, "cert_asset_invalid")
    kind = await admin.post(url, files=upload(png()), data={"kind": "seal"})
    assert kind.status_code == 422
    assert (await admin.post(url, files=upload(png()))).status_code == 422
    texts = await log_texts(admin)
    assert any("загружено изображение для сертификатов" in t for t in texts)


async def test_asset_get_headers_and_kinds(admin: httpx.AsyncClient) -> None:
    aid = await asset(admin, "image", SVG)
    r = await admin.get(f"/api/v1/cert-assets/{aid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/svg+xml"
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"
    pid = await asset(admin, "background", png((7, 7, 7)))
    assert (await admin.get(f"/api/v1/cert-assets/{pid}")).headers["content-type"] == "image/png"
    await sql("UPDATE cert_asset SET kind = 'logo' WHERE id = :i", i=pid)
    assert (await admin.get(f"/api/v1/cert-assets/{pid}")).status_code == 404
    gone = "00000000-0000-0000-0000-000000000001"
    assert (await admin.get(f"/api/v1/cert-assets/{gone}")).status_code == 404


async def test_fields_catalog(admin: httpx.AsyncClient) -> None:
    r = await admin.get("/api/v1/cert-fields")
    assert r.status_code == 200
    body = r.json()
    by_key = {f["key"]: f for f in body["fields"]}
    assert by_key["student.full_name"]["group"] == "Студент"
    assert by_key["student.full_name"]["label"] == "ФИО студента"
    assert by_key["course.name"]["group"] == "Курс и поток"
    assert by_key["instructor.full_name"]["group"] == "Инструктор"
    assert by_key["certificate.number"]["group"] == "Сертификат"
    assert by_key["company.director_name"]["group"] == "Директор"
    assert by_key["certificate.issued_date"]["type"] == "date"
    assert set(body["samples"]) == {"short", "long", "female"}
    for sample in body["samples"].values():
        assert set(by_key) <= set(sample) and sample["gender"] in ("male", "female")
    assert body["samples"]["female"]["gender"] == "female"
    assert body["samples"]["short"]["student.full_name"] == "Каримов Али"
    assert body["fonts"][0] == {
        "family": "Montserrat",
        "weights": [400, 500, 600, 700, 800],
        "italic_weights": [400, 700],
    }
    assert body["date_formats"] == ["dd.mm.yyyy", "d month yyyy", "month d, yyyy"]


async def test_fonts(admin: httpx.AsyncClient) -> None:
    r = await admin.get("/api/v1/cert-fonts/Montserrat-700.ttf")
    assert r.status_code == 200 and r.headers["content-type"] == "font/ttf"
    assert "max-age=31536000" in r.headers["cache-control"] and r.content[:4] == b"\x00\x01\x00\x00"
    for name in ("Nope.ttf", "..%2F..%2Fmain.py", "..%2FOFL.txt", "OFL.txt", "Montserrat-900.ttf"):
        assert (await admin.get(f"/api/v1/cert-fonts/{name}")).status_code == 404, name
    assert (await admin.get("/api/v1/cert-fonts/../fonts.py")).status_code == 404


async def test_rules_replace_and_validation(admin: httpx.AsyncClient) -> None:
    url = "/api/v1/cert-template-rules"
    t = await new(admin, "Для Python")
    t2 = await new(admin, "Для Java")
    course = str(await make_course("Python"))
    other = str(await make_course("Java"))
    teacher = str(await make_user("teacher", "instructor"))
    rules = [
        {"course_id": course, "instructor_id": None, "template_id": t["id"]},
        {"course_id": course, "instructor_id": teacher, "template_id": t2["id"]},
        {"course_id": other, "template_id": t2["id"]},
    ]
    r = await admin.put(url, json={"rules": rules}, no_version=True)
    assert r.status_code == 200, r.text
    names = {
        (x["course_name"], x["instructor_name"], x["template_name"]) for x in r.json()["rules"]
    }
    assert len(names) == 3 and ("Python", None, "Для Python") in names
    assert (await admin.get(url)).json() == r.json()
    detail = (await admin.get(f"{T}/{t2['id']}")).json()
    assert {x["course_name"] for x in detail["rules"]} == {"Python", "Java"}
    assert all(
        set(x) == {"course_id", "course_name", "instructor_id", "instructor_name"}
        for x in detail["rules"]
    )
    dup = await admin.put(url, json={"rules": [rules[0], rules[0]]}, no_version=True)
    assert (dup.status_code, dup.json()["code"]) == (409, "cert_rule_duplicate")
    gone = await admin.put(
        url,
        json={
            "rules": [{"course_id": "00000000-0000-0000-0000-000000000001", "template_id": t["id"]}]
        },
        no_version=True,
    )
    assert (gone.status_code, gone.json()["code"]) == (422, "cert_rule_invalid")
    await admin.patch(f"{T}/{t['id']}", json={"status": "archived"})
    arch = await admin.put(url, json={"rules": rules[:1]}, no_version=True)
    assert (arch.status_code, arch.json()["code"]) == (422, "cert_rule_invalid")
    assert len((await admin.get(url)).json()["rules"]) == 3  # failed replace changed nothing
    ok = await admin.put(url, json={"rules": rules[2:]}, no_version=True)
    assert len(ok.json()["rules"]) == 1
    assert (await admin.put(url, json={"rules": []}, no_version=True)).json() == {"rules": []}


async def test_every_write_is_audited_in_russian(admin: httpx.AsyncClient) -> None:
    t = await new(admin, "Журнал")
    url = f"{T}/{t['id']}"
    await admin.patch(url, json={"status": "archived", "name": "Журнал 2"})
    ref = await asset(admin)
    await admin.patch(url, json={"draft": with_bg(layout(None, text_layer("name")), ref)})
    await admin.post(f"{url}/publish")
    v = (await admin.get(url)).json()["version"]
    await admin.post(f"{url}/restore/1", headers={"X-Record-Version": str(v)})
    course = str(await make_course("Журнальный"))
    await admin.put("/api/v1/cert-template-rules", json={"rules": []}, no_version=True)
    rows = await sql("SELECT action, entity, label, diff FROM audit_log ORDER BY at, id")
    actions = [r[0] for r in rows if r[1].startswith("cert_")]
    assert actions == [
        "cert_template.create", "cert_template.update", "cert_asset.upload",
        "cert_template.draft_update", "cert_template.publish_version", "cert_template_rule.replace",
    ]  # fmt: skip
    assert course
    draft_row = next(r for r in rows if r[0] == "cert_template.draft_update")
    assert draft_row[3] == {}  # no JSON in the log
    texts = await log_texts(admin)
    for expected in (
        "создан шаблон сертификата Журнал",
        "изменён шаблон сертификата Журнал 2",
        "изменён черновик шаблона Журнал 2",
        "опубликована версия 1 шаблона Журнал 2",
        "загружено изображение для сертификатов",
        "изменены правила выбора шаблона сертификата",
    ):
        assert any(expected in x for x in texts), expected


async def test_restore_is_audited(admin: httpx.AsyncClient) -> None:
    t = await new(admin, "Возврат")
    url = f"{T}/{t['id']}"
    d = deepcopy(t["draft"])
    d["layers"].append({"id": "qr", "type": "qr", "x_mm": 5, "y_mm": 5, "w_mm": 20, "h_mm": 20})
    saved = (await admin.patch(url, json={"draft": d})).json()["draft"]
    await admin.post(f"{url}/publish")
    await admin.patch(url, json={"draft": t["draft"]})
    v = (await admin.get(url)).json()["version"]
    r = await admin.post(f"{url}/restore/1", headers={"X-Record-Version": str(v)})
    assert r.status_code == 200 and r.json()["draft"] == saved
    texts = await log_texts(admin)
    assert any("черновик шаблона Возврат восстановлен из версии 1" in x for x in texts)
