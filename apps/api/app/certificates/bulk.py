"""Bulk issue of certificates from an Excel list (stage C5).

For people who may not be students (an outside event). The list is uploaded twice, stateless: once
for the preview (rows OK / with a reason / duplicates), once to issue, which parses and validates
again so the preview can never be stale. Every cell is untrusted text. Issuing goes through the
same pieces as the group issue (chosen template, pinned version, `fix_of`, one numbering, the
snapshot, audit); a certificate of a batch has no enrollment, only a branch, an optional linked
student (by phone, inside the branch) and the batch id.

Rights: `certificates` change, never an instructor, branch-scoped like the group issue; the ZIP of a
batch needs view.
"""

import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.auth.deps import Principal, require, require_csrf_header
from app.certificates.api import file_name
from app.certificates.errors import (
    CERT_BRANCH_REQUIRED,
    CERT_BULK_EMPTY,
    CERT_BULK_FILE,
)
from app.certificates.fields import Context, apply_settings, image_refs, load_settings, split_name
from app.certificates.fields import snapshot_of
from app.certificates.issuing import (
    PLACEHOLDER_NUMBER,
    AssetCache,
    chosen_template,
    fix_of,
    layout_of,
    new_verify_code,
    published_version,
)
from app.certificates.registry import BULK_LABEL
from app.certificates.stored import render_certificate
from app.core import clock
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.education.scope import is_instructor, writer
from app.export import XLSX
from app.graduates.numbering import new_number
from app.leads.hygiene import normalise_phone
from app.models import Branch, Certificate, CertTemplate, CertTemplateVersion, Student

router = APIRouter(
    prefix="/api/v1", tags=["certificates"], dependencies=[Depends(require_csrf_header)]
)

Change = Annotated[Principal, writer("certificates")]
View = Annotated[Principal, require("certificates", "view")]
Lang = Literal["ru", "en", "tg"]

MAX_ROWS = 500
MAX_SCANNED = 5_000  # rows looked at, empty ones included: an «empty» sheet cannot spin forever
MAX_BYTES = 2 * 1024 * 1024
MAX_NAME = 150
MAX_COURSE = 200
EARLIEST = date(2000, 1, 1)

HEADERS = ("ФИО", "Курс/название", "Дата выдачи", "Телефон", "Пол")
# normalised header -> field
_ALIASES = {
    "фио": "name",
    "курс/название": "course",
    "курс": "course",
    "название": "course",
    "датавыдачи": "date",
    "дата": "date",
    "телефон": "phone",
    "пол": "gender",
}
_GENDERS = {
    "м": "male", "муж": "male", "мужской": "male", "m": "male", "male": "male",
    "ж": "female", "жен": "female", "женский": "female", "f": "female", "female": "female",
}  # fmt: skip
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass
class Row:
    number: int  # the row in the sheet (the header is row 1)
    name: str = ""
    course: str = ""
    issued: date | None = None
    phone: str | None = None
    gender: str | None = None
    student_id: uuid.UUID | None = None
    status: Literal["ok", "error", "duplicate"] = "ok"
    reason: str | None = None
    note: str | None = None
    ctx: Context | None = field(default=None, repr=False)

    def fail(self, reason: str, status: Literal["error", "duplicate"] = "error") -> None:
        if self.status == "ok":  # the first reason stays
            self.status, self.reason = status, reason


def _clean(value: Any, limit: int) -> tuple[str, bool]:
    """(text, too long): a cell as plain text: control characters dropped, spaces collapsed."""
    if value is None:
        return "", False
    raw = value.isoformat() if isinstance(value, datetime | date) else str(value)
    plain = " ".join(_CONTROL.sub(" ", raw).split())
    return plain[:limit], len(plain) > limit


def _header_key(value: Any) -> str:
    return "".join(str(value or "").lower().replace("*", "").split())


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    plain = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(plain, fmt).date()
        except ValueError:
            continue
    raise ValueError(plain)


def _read_sheet(data: bytes) -> list[tuple[int, dict[str, Any]]]:
    """[(row number, {field: raw cell})] of the non-empty rows. Runs in a thread."""
    from openpyxl import load_workbook

    if not data.startswith(b"PK\x03\x04"):
        raise DomainError(CERT_BULK_FILE, reason="not_xlsx")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(min_row=1, max_col=len(HEADERS), values_only=True)
        head = next(rows, None)
        if head is None:
            raise DomainError(CERT_BULK_FILE, reason="empty")
        columns = {i: _ALIASES[k] for i, h in enumerate(head) if (k := _header_key(h)) in _ALIASES}
        if "name" not in columns.values():
            raise DomainError(CERT_BULK_FILE, reason="no_name_column")
        out: list[tuple[int, dict[str, Any]]] = []
        for scanned, cells in enumerate(rows, start=2):
            if scanned > MAX_SCANNED:
                raise DomainError(CERT_BULK_FILE, reason="too_many_rows", max=MAX_ROWS)
            item = {columns[i]: v for i, v in enumerate(cells) if i in columns}
            if all(v is None or not str(v).strip() for v in item.values()):
                continue
            if len(out) >= MAX_ROWS:
                raise DomainError(CERT_BULK_FILE, reason="too_many_rows", max=MAX_ROWS)
            out.append((scanned, item))
        wb.close()
    except DomainError:
        raise
    except Exception:  # a broken, encrypted or non-spreadsheet zip
        raise DomainError(CERT_BULK_FILE, reason="not_xlsx") from None
    if not out:
        raise DomainError(CERT_BULK_FILE, reason="empty")
    return out


def _row_of(number: int, item: dict[str, Any], today: date) -> Row:
    row = Row(number)
    row.name, long_name = _clean(item.get("name"), MAX_NAME)
    row.course, long_course = _clean(item.get("course"), MAX_COURSE)
    if len(row.name) < 2:
        row.fail("Не указано ФИО")
    elif long_name:
        row.fail(f"ФИО длиннее {MAX_NAME} знаков")
    if long_course:
        row.fail(f"Название курса длиннее {MAX_COURSE} знаков")
    raw_date = item.get("date")
    if raw_date is None or not str(raw_date).strip():
        row.issued = today
    else:
        try:
            row.issued = _parse_date(raw_date)
        except ValueError:
            row.fail("Дата выдачи не распознана: нужен формат ДД.ММ.ГГГГ")
        else:
            if row.issued > today:
                row.fail("Дата выдачи в будущем")
            elif row.issued < EARLIEST:
                row.fail("Дата выдачи слишком ранняя")
    raw_gender, _ = _clean(item.get("gender"), 20)
    if raw_gender:
        row.gender = _GENDERS.get(raw_gender.lower().rstrip("."))
        if row.gender is None:
            row.fail("Пол: укажите «м» или «ж»")
    raw_phone, _ = _clean(item.get("phone"), 40)
    if raw_phone:
        row.phone = normalise_phone(raw_phone)
        if row.phone is None:
            row.note = "Телефон не распознан: сертификат без привязки к студенту"
    return row


def _key(name: str, course: str) -> tuple[str, str]:
    return name.casefold(), course.casefold()


@dataclass
class Analysis:
    rows: list[Row]
    branch: Branch
    template_id: uuid.UUID
    template_key: str
    template_name: str
    version_id: uuid.UUID
    lang: str
    verify_base: str


async def _branch_of(db: AsyncSession, p: Principal, branch_id: uuid.UUID | None) -> Branch:
    if branch_id is not None:
        p.check_scope(branch_id)
    target = p.branch_id or branch_id
    if target is None:
        raise DomainError(CERT_BRANCH_REQUIRED)
    branch = await db.get(Branch, target)
    if branch is None:
        raise DomainError(NOT_FOUND)
    return branch


async def _analyse(
    db: AsyncSession,
    p: Principal,
    file: UploadFile,
    template_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    lang: str | None,
) -> Analysis:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise DomainError(CERT_BULK_FILE, reason="too_large", max_bytes=MAX_BYTES)
    branch = await _branch_of(db, p, branch_id)
    template = await chosen_template(db, template_id)
    version = await published_version(db, template)
    layout = layout_of(version)
    lang_code: str = lang or template.lang
    sheet = await anyio.to_thread.run_sync(_read_sheet, data)
    today = clock.today()
    rows = [_row_of(n, item, today) for n, item in sheet]

    # people in this branch only: a phone of another branch never links
    phones = {r.phone for r in rows if r.phone}
    students: dict[str, Student] = {}
    if phones:
        found = await db.execute(
            select(Student).where(Student.phone.in_(phones), Student.branch_id == branch.id)
        )
        students = {s.phone: s for s in found.scalars() if s.phone}

    # the same holder and course already holds a valid certificate in the branch
    names = {r.name.casefold() for r in rows if r.status == "ok"}
    held: set[tuple[str, str]] = set()
    if names:
        name_in = Certificate.data["values"]["student.full_name"].as_string()
        course_in = Certificate.data["values"]["course.name"].as_string()
        for n, c in await db.execute(
            select(name_in, func.coalesce(course_in, "")).where(
                Certificate.branch_id == branch.id,
                Certificate.status == "valid",
                func.lower(name_in).in_(names),
            )
        ):
            held.add(_key(n or "", c or ""))

    settings_row = await load_settings(db)
    verify_base = (settings_row.verify_base_url or "").rstrip("/")
    cache = AssetCache(db)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.status != "ok":
            continue
        key = _key(row.name, row.course)
        if key in seen:
            row.fail("Повтор строки списка: такое ФИО и курс уже есть выше", "duplicate")
            continue
        seen.add(key)
        if key in held:
            row.fail("Сертификат этому человеку по этому курсу уже выдан", "duplicate")
            continue
        student = students.get(row.phone or "")
        if student is not None:
            row.student_id = student.id
            row.gender = row.gender or student.gender
        first, last = split_name(row.name)
        ctx = Context(
            values={
                "student.full_name": row.name,
                "student.first_name": first,
                "student.last_name": last,
                "course.name": row.course,
                "course.direction": "",
                "cohort.code": "",
                "branch.name": branch.name,
                "instructor.full_name": "",
                "certificate.number": PLACEHOLDER_NUMBER,
                "certificate.issued_date": row.issued or today,
                "grade.total": "",
            },
            gender=row.gender,
            verify_base=verify_base,
        )
        apply_settings(ctx, settings_row, lang_code)
        assets = await cache.get([*layout.asset_refs(), *image_refs(ctx)])
        if fix := fix_of(layout, ctx, assets):
            row.fail(fix.text)
            continue
        row.ctx = ctx
    return Analysis(
        rows, branch, template.id, template.key, template.name, version.id, lang_code, verify_base
    )


def _item(r: Row) -> dict[str, Any]:
    return {
        "row": r.number,
        "name": r.name,
        "course": r.course or None,
        "issued_date": r.issued,
        "phone": r.phone,
        "status": r.status,
        "reason": r.reason,
        "note": r.note,
        "linked": r.student_id is not None,
    }


def _counts(rows: list[Row]) -> dict[str, int]:
    return {s: sum(1 for r in rows if r.status == s) for s in ("ok", "error", "duplicate")}


@router.get("/certificates/bulk/templates")
async def templates(p: Change, db: DB) -> dict[str, Any]:
    """Templates the issuer may choose from (active, with a published version): id, name, language.
    The issue right is enough; the template editor's right is not needed."""
    rows = (
        await db.execute(
            select(CertTemplate.id, CertTemplate.name, CertTemplate.lang)
            .where(
                CertTemplate.status == "active",
                select(CertTemplateVersion.id)
                .where(CertTemplateVersion.template_id == CertTemplate.id)
                .exists(),
            )
            .order_by(CertTemplate.name)
        )
    ).all()
    return {"items": [{"id": r.id, "name": r.name, "lang": r.lang} for r in rows]}


@router.get("/certificates/bulk/template")
async def template_file(p: Change) -> Response:
    """The empty list to fill in: Russian headers, a second sheet that explains them."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Список"
    ws.append(list(HEADERS))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for letter, width in zip("ABCDE", (36, 32, 16, 20, 10), strict=True):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2, max_row=MAX_ROWS + 1, min_col=3, max_col=4):
        row[0].number_format = "dd.mm.yyyy"
        row[1].number_format = "@"
    help_ws = wb.create_sheet("Как заполнить")
    for line in (
        ("ФИО", "Обязательно. Как печатать на сертификате."),
        ("Курс/название", "Необязательно. Курс, мероприятие или программа."),
        ("Дата выдачи", "Необязательно, ДД.ММ.ГГГГ. Пусто: сегодняшняя дата."),
        (
            "Телефон",
            "Необязательно. Если совпал со студентом вашего филиала, сертификат "
            "привязывается к нему.",
        ),
        ("Пол", "Необязательно: м или ж. Нужен, если шаблон склоняет слова по полу."),
        ("", f"Не больше {MAX_ROWS} строк. Заполняйте первый лист."),
    ):
        help_ws.append(list(line))
    help_ws.column_dimensions["A"].width = 18
    help_ws.column_dimensions["B"].width = 90
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="sertifikaty-shablon.xlsx"'},
    )


Upload = Annotated[UploadFile, File()]
TemplateId = Annotated[uuid.UUID, Form()]
BranchId = Annotated[uuid.UUID | None, Form()]
LangForm = Annotated[Lang | None, Form()]


@router.post("/certificates/bulk/preview")
async def preview(
    p: Change,
    db: DB,
    file: Upload,
    template_id: TemplateId,
    branch_id: BranchId = None,
    lang: LangForm = None,
) -> dict[str, Any]:
    """Parse and check the list. Writes nothing: no number, no row, no audit entry."""
    a = await _analyse(db, p, file, template_id, branch_id, lang)
    return {
        "template_id": a.template_id,
        "template_name": a.template_name,
        "branch_id": a.branch.id,
        "branch_name": a.branch.name,
        "lang": a.lang,
        "counts": _counts(a.rows),
        "linked": sum(1 for r in a.rows if r.student_id is not None),
        "items": [_item(r) for r in a.rows],
    }


@router.post("/certificates/bulk/issue", status_code=201)
async def issue(
    p: Change,
    db: DB,
    file: Upload,
    template_id: TemplateId,
    branch_id: BranchId = None,
    lang: LangForm = None,
) -> dict[str, Any]:
    """One transaction: every OK row is issued, the other rows are reported and skipped. Nothing
    OK is a 409. Two lists of one branch never run together (an advisory lock), so the duplicate
    check cannot be raced."""
    branch = await _branch_of(db, p, branch_id)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"cert_bulk:{branch.id}"}
    )
    a = await _analyse(db, p, file, template_id, branch_id, lang)
    good = [r for r in a.rows if r.status == "ok" and r.ctx is not None]
    if not good:
        raise DomainError(CERT_BULK_EMPTY, items=[_item(r) for r in a.rows])
    batch_id = uuid.uuid4()
    issued_at = clock.now()
    created: list[dict[str, Any]] = []
    for row in good:
        ctx = row.ctx
        assert ctx is not None
        number = await new_number(db, issued_at)
        code = new_verify_code()
        ctx.values["certificate.number"] = number
        ctx.verify_code = code if ctx.verify_base else number
        cert = Certificate(
            number=number,
            verify_code=code,
            student_id=row.student_id,
            batch_id=batch_id,
            branch_id=a.branch.id,
            template_id=a.template_id,
            template_version_id=a.version_id,
            lang=a.lang,
            data=snapshot_of(ctx, a.lang, {}),
            status="valid",
            issued_at=issued_at,
            issued_by=p.id,
        )
        db.add(cert)
        await db.flush()
        await record(
            db, p.id, "certificate.issue", "certificate", cert.id,
            {
                "number": [None, number], "template": [None, a.template_key],
                "bulk": [None, True],
            },
            branch_id=a.branch.id, label=f"{row.name} ({BULK_LABEL})",
        )  # fmt: skip
        created.append(
            {
                "id": cert.id,
                "row": row.number,
                "number": number,
                "student_name": row.name,
                "linked": row.student_id is not None,
            }
        )
    skipped = [_item(r) for r in a.rows if r not in good]
    source = _clean((file.filename or "").rsplit("/", 1)[-1], 100)[0] or "список.xlsx"
    await record(
        db, p.id, "certificate.bulk_issue", "certificate", batch_id,
        {
            "count": [None, len(created)], "skipped": [None, len(skipped)],
            "template": [None, a.template_key],
        },
        branch_id=a.branch.id, label=source,
    )  # fmt: skip
    return {
        "batch_id": batch_id,
        "count": len(created),
        "items": created,
        "skipped": skipped,
    }


@router.get("/certificates/bulk/{batch_id}/zip")
async def batch_zip(batch_id: uuid.UUID, p: View, db: DB) -> Response:
    """The PDFs of one batch in a ZIP (rendered from what was stored at issue)."""
    certs = list(
        (
            await db.execute(
                select(Certificate)
                .where(Certificate.batch_id == batch_id)
                .order_by(Certificate.number)
            )
        ).scalars()
    )
    if not certs or is_instructor(p):
        raise DomainError(NOT_FOUND)
    p.check_scope(certs[0].branch_id)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for cert in certs:
            name = str(cert.data["values"].get("student.full_name", ""))
            z.writestr(file_name(cert.number, name), await render_certificate(db, cert))
    await record(
        db, p.id, "certificate.bulk_zip", "certificate", batch_id,
        {"count": [None, len(certs)]}, branch_id=certs[0].branch_id, label=f"{len(certs)}",
    )  # fmt: skip
    return Response(
        out.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="sertifikaty-{batch_id}.zip"'},
    )
