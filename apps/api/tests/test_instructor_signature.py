"""Instructor signature for certificates: upload / preview / read / delete, rights and scope,
the renderer drawing it for a graduate, and the importer (`instructors.json`)."""

import io
import json
import uuid
from pathlib import Path

import httpx
from PIL import Image
from pypdf import PdfReader

from app.audit.sentences import Entry, sentence
from app.certificates.importer import Counts, import_instructor_signatures
from app.core.db import sessionmaker
from tests.certs import layout, make_template, text_layer
from tests.conftest import SignedIn, make_role, make_user, sql
from tests.reports import G
from tests.test_cert_settings import files, photo, transparent_png
from tests.test_certificates import certify, graduate

I = "/api/v1/instructors"  # noqa: E741


async def instructor(
    login: str, branch: str | None = "Душанбе", name: str | None = None
) -> uuid.UUID:
    uid = await make_user(login, "instructor", branch=branch)
    if name:
        await sql("UPDATE app_user SET full_name = :n WHERE id = :i", n=name, i=uid)
    return uid


async def test_rights_view_only_and_the_instructor_role_never_write(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    uid = await instructor("ins1")
    nobody = await login_as("n", await make_role("Без", {"graduates": "change"}))
    assert (await nobody.post(f"{I}/{uid}/signature", files=files(photo()))).status_code == 403
    assert (
        await nobody.post(f"{I}/{uid}/signature/preview", files=files(photo()))
    ).status_code == 403
    assert (await nobody.get(f"{I}/{uid}/signature")).status_code == 403
    assert (await nobody.delete(f"{I}/{uid}/signature")).status_code == 403
    viewer = await login_as("v", await make_role("Смотрит", {"instructors": "view"}))
    assert (await viewer.post(f"{I}/{uid}/signature", files=files(photo()))).status_code == 403
    assert (await viewer.delete(f"{I}/{uid}/signature")).status_code == 403
    assert (await viewer.get(f"{I}/{uid}/signature")).status_code == 404  # none yet
    assert (await admin.post(f"{I}/{uid}/signature", files=files(photo()))).status_code == 200
    assert (await viewer.get(f"{I}/{uid}/signature")).status_code == 200
    ins = await login_as("insself", "instructor", branch="Душанбе")
    assert (await ins.post(f"{I}/{uid}/signature", files=files(photo()))).status_code in (403, 404)


async def test_scope_by_branch(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    other = await instructor("ist1", branch="Истаравшан")
    everywhere = await instructor("all1", branch=None)
    manager = await login_as(
        "mgr", await make_role("Меняет", {"instructors": "change"}), branch="Душанбе"
    )
    assert (await manager.post(f"{I}/{other}/signature", files=files(photo()))).status_code == 404
    assert (await manager.get(f"{I}/{other}/signature")).status_code == 404
    # an instructor of all branches: visible, but not writable by a branch-bound manager
    r = await manager.post(f"{I}/{everywhere}/signature", files=files(photo()))
    assert r.status_code == 403 and r.json()["code"] == "branch_forbidden"
    assert (await admin.post(f"{I}/{other}/signature", files=files(photo()))).status_code == 200


async def test_upload_preview_read_and_delete(admin: httpx.AsyncClient) -> None:
    uid = await instructor("ins2", name="Бобоев Джамшед")
    assert (await admin.get(f"{I}/{uid}")).json()["has_signature"] is False
    p = await admin.post(
        f"{I}/{uid}/signature/preview", files=files(photo(), "p.jpg", "image/jpeg")
    )
    assert p.status_code == 200 and p.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(p.content)).mode == "RGBA"
    assert (await sql("SELECT count(*) FROM cert_asset"))[0][0] == 0  # preview saves nothing
    r = await admin.post(
        f"{I}/{uid}/signature", files=files(photo(), "p.jpg", "image/jpeg"), params={"ink": "blue"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_signature"] is True
    listed = (await admin.get(I)).json()["items"]
    assert [i["has_signature"] for i in listed if i["id"] == str(uid)] == [True]
    got = await admin.get(f"{I}/{uid}/signature")
    assert got.headers["content-type"] == "image/png" and got.content[:4] == b"\x89PNG"
    kind = (await sql("SELECT kind FROM cert_asset"))[0][0]
    assert kind == "signature"
    bad = await admin.post(f"{I}/{uid}/signature", files=files(b"not an image"))
    assert bad.status_code == 422
    assert (
        await admin.post(f"{I}/{uid}/signature?ink=red", files=files(photo()))
    ).status_code == 422
    d = await admin.delete(f"{I}/{uid}/signature")
    assert d.status_code == 200 and d.json()["has_signature"] is False
    assert (await admin.get(f"{I}/{uid}/signature")).status_code == 404
    await admin.delete(f"{I}/{uid}/signature")  # nothing to remove: no second audit entry
    rows = await sql(
        "SELECT action, entity, label, diff FROM audit_log WHERE action LIKE 'instructor.signature%' ORDER BY at"
    )
    assert [r[0] for r in rows] == ["instructor.signature_upload", "instructor.signature_delete"]
    assert (
        sentence(Entry("А", *rows[0]))
        == "А: загружена подпись инструктора Бобоев Джамшед для сертификатов"
    )
    assert (
        sentence(Entry("А", *rows[1]))
        == "А: удалена подпись инструктора Бобоев Джамшед для сертификатов"
    )


def images_in(pdf: bytes) -> int:
    return sum(len(page.images) for page in PdfReader(io.BytesIO(pdf)).pages)


async def test_the_graduate_pdf_draws_the_cohort_instructors_signature(
    admin: httpx.AsyncClient,
) -> None:
    uid = await instructor("ins3", name="Каримов Карим")
    sig_layer = {
        "id": "isig", "type": "image", "x_mm": 150, "y_mm": 150, "w_mm": 40, "h_mm": 20,
        "source": {"signature": "instructor"},
    }  # fmt: skip
    name_layer = text_layer("iname", {"field": "instructor.full_name"}, size_pt=12)
    await make_template(lay=layout("bg.png", sig_layer, name_layer))
    _, eid = await graduate(admin, instructor_id=str(uid))
    await certify(admin, eid)
    plain = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert plain.status_code == 200 and images_in(plain.content) == 1  # the background only
    other = await instructor("ins4", name="Другой Человек")
    await admin.post(f"{I}/{other}/signature", files=files(transparent_png()))
    still = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert images_in(still.content) == 1  # someone else's signature is not drawn
    up = await admin.post(f"{I}/{uid}/signature", files=files(transparent_png()))
    assert up.status_code == 200
    drawn = await admin.get(f"{G}/{eid}/certificate/pdf")
    assert drawn.status_code == 200 and images_in(drawn.content) == 2
    # a sample preview has no instructor: nothing is drawn
    tid = (await sql("SELECT id FROM cert_template LIMIT 1"))[0][0]
    sample = await admin.post(f"/api/v1/cert-templates/{tid}/preview")
    assert sample.status_code == 200 and images_in(sample.content) == 1


async def run_import(images: Path) -> Counts:
    counts = Counts()
    async with sessionmaker() as db:
        await import_instructor_signatures(db, images, counts)
        await db.commit()
    return counts


async def test_import_matches_names_in_either_order_and_never_overwrites(
    admin: httpx.AsyncClient, tmp_path: Path
) -> None:
    jam = await instructor("imp1", name="Бобоев Джамшед")
    zar = await instructor("imp2", name="Олимов Зарифхон")
    mine = await instructor("imp3", name="Свой Подписал")
    (tmp_path / "instructors").mkdir()
    for n in ("a", "b", "c"):
        (tmp_path / "instructors" / f"{n}.png").write_bytes(transparent_png())
    assert (await run_import(tmp_path)).signatures_assigned == 0  # no instructors.json
    await admin.post(f"{I}/{mine}/signature", files=files(photo(), "p.jpg", "image/jpeg"))
    before = (await sql("SELECT signature_asset_id FROM app_user WHERE id = :i", i=mine))[0][0]
    (tmp_path / "instructors.json").write_text(
        json.dumps([
            {"full_name": "бобоев ДЖАМШЕД", "signature": "instructors/a.png"},
            {"full_name": "Зарифхон Олимов", "signature": "instructors/b.png"},  # reversed order
            {"full_name": "Свой Подписал", "signature": "instructors/c.png"},  # has one already
            {"full_name": "Никто Такой", "signature": "instructors/a.png"},
        ])
    )  # fmt: skip
    counts = await run_import(tmp_path)
    assert counts.signatures_assigned == 2
    assert counts.signatures_unmatched == ["Никто Такой"]
    rows = dict((str(r[0]), r[1]) for r in await sql("SELECT id, signature_asset_id FROM app_user"))
    assert rows[str(jam)] is not None and rows[str(zar)] is not None
    assert rows[str(mine)] == before  # the CRM's signature stays
    again = await run_import(tmp_path)  # a second run changes nothing
    assert again.signatures_assigned == 0
    assert (
        await sql("SELECT count(*) FROM audit_log WHERE action = 'instructor.signature_upload'")
    )[0][0] == 3  # the CRM upload and two imports


async def test_import_refuses_a_bad_file(tmp_path: Path) -> None:
    import pytest

    from app.certificates.importer import ImportProblem

    (tmp_path / "instructors.json").write_text(json.dumps({"full_name": "x"}))
    with pytest.raises(ImportProblem):
        await run_import(tmp_path)
    (tmp_path / "instructors.json").write_text(
        json.dumps([{"full_name": "Бобоев Джамшед", "signature": "missing.png"}])
    )
    await instructor("imp9", name="Бобоев Джамшед")
    with pytest.raises(ImportProblem):
        await run_import(tmp_path)
