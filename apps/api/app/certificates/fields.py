"""The field catalog: the ONLY source of values a template can show. Template text is never
evaluated; a `field` run names a key from `FIELDS` and nothing else.

Name rule: the CRM keeps a student's name as «Фамилия Имя Отчество...» (surname first), so
`student.last_name` is the first word and `student.first_name` is everything after it. A
one-word name has the whole name as last name and an empty first name.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import TZ
from app.core.errors import NOT_FOUND, DomainError
from app.metrics.attendance import enrollment_results
from app.models import AppUser, Branch, CertSettings, Cohort, Course, Enrollment, Student

# key -> Russian label (for the editor of stage C4)
FIELDS: dict[str, str] = {
    "student.full_name": "ФИО студента",
    "student.first_name": "Имя студента",
    "student.last_name": "Фамилия студента",
    "course.name": "Курс",
    "course.direction": "Направление",
    "cohort.code": "Код потока",
    "cohort.start_date": "Начало потока",
    "cohort.end_date": "Конец потока",
    "branch.name": "Филиал",
    "instructor.full_name": "Инструктор",
    "certificate.number": "Номер сертификата",
    "certificate.issued_date": "Дата выдачи",
    "grade.total": "Итоговый балл",
    "company.director_name": "Директор: имя",
    "company.director_title": "Директор: должность",
}
DATE_FORMATS = ("dd.mm.yyyy", "d month yyyy", "month d, yyyy")
DEFAULT_DATE_FORMAT = DATE_FORMATS[0]
_RU_MONTHS = (
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
)
_EN_MONTHS = (
    "January February March April May June July August September October November December"
).split()


def format_date(value: date, fmt: str | None) -> str:
    fmt = fmt or DEFAULT_DATE_FORMAT
    if fmt == "d month yyyy":
        return f"{value.day} {_RU_MONTHS[value.month - 1]} {value.year}"
    if fmt == "month d, yyyy":
        return f"{_EN_MONTHS[value.month - 1]} {value.day}, {value.year}"
    return f"{value.day:02d}.{value.month:02d}.{value.year}"


def split_name(full_name: str) -> tuple[str, str]:
    """(first name, last name) of «Фамилия Имя ...»."""
    words = full_name.split()
    return " ".join(words[1:]), words[0] if words else ""


@dataclass
class Context:
    """Values of one certificate. Dates stay dates until a run formats them."""

    values: dict[str, str | date] = field(default_factory=dict)
    gender: str | None = None  # 'male' | 'female' | None
    verify_code: str = ""  # goes into the QR link
    verify_base: str = ""  # origin of the QR link; empty = the configured default
    signature_ref: str | None = None  # asset id of the director's signature
    seal_ref: str | None = None  # asset id of the company seal
    instructor_signature_ref: str | None = None  # asset id of the cohort instructor's signature


async def load_settings(db: AsyncSession) -> CertSettings:
    return (await db.execute(select(CertSettings).where(CertSettings.id == 1))).scalar_one()


def director_for(row: CertSettings, lang: str) -> tuple[str, str]:
    """(name, title) of the director in a template language; an empty variant is the Russian one."""
    name, title = row.director_name, row.director_title
    if lang in ("en", "tg"):
        name = getattr(row, f"director_name_{lang}") or name
        title = getattr(row, f"director_title_{lang}") or title
    return name, title


def apply_settings(ctx: Context, row: CertSettings, lang: str = "ru") -> Context:
    """Put the director of the settings row into a context, in the template's language."""
    ctx.values["company.director_name"], ctx.values["company.director_title"] = director_for(
        row, lang
    )
    ctx.signature_ref = str(row.director_signature_asset_id or "") or None
    ctx.seal_ref = str(row.seal_asset_id or "") or None
    return ctx


def image_refs(ctx: Context) -> list[str]:
    """Asset ids a render of this context may draw: the director's signature and seal, and the
    instructor's signature."""
    refs = (ctx.signature_ref, ctx.seal_ref, ctx.instructor_signature_ref)
    return [r for r in refs if r]


def sample_context(kind: str) -> Context:
    names = {
        "short": ("Каримов Али", "male"),
        "long": ("Абдурахмонзода Мухаммадджон", "male"),
        "female": ("Раҳимова Ҳалимаи Ҷамшед", "female"),
    }
    full, gender = names[kind]
    first, last = split_name(full)
    return Context(
        values={
            "student.full_name": full,
            "student.first_name": first,
            "student.last_name": last,
            "course.name": "Веб-разработка",
            "course.direction": "IT",
            "cohort.code": "G-001",
            "cohort.start_date": date(2026, 3, 2),
            "cohort.end_date": date(2026, 11, 18),
            "branch.name": "Душанбе",
            "instructor.full_name": "Назаров Фаррух",
            "certificate.number": "CERT-2026-0001",
            "certificate.issued_date": date(2026, 11, 18),
            "grade.total": "95",
            "company.director_name": "Директор Образцов",
            "company.director_title": "Директор ОО Илмхона",
        },
        gender=gender,
        verify_code="SAMPLE",
    )


SAMPLE_KINDS = ("short", "long", "female")


async def enrollment_context(
    db: AsyncSession, enrollment_id: Any, lang: str = "ru"
) -> tuple[Context, Cohort, Course, AppUser | None, Enrollment]:
    """Everything a certificate shows, from one enrollment (enrollment -> student, cohort ->
    course, branch, instructor). The total comes from `app.metrics`, never recomputed."""
    row = (
        await db.execute(
            select(Enrollment, Student, Cohort, Course, Branch, AppUser)
            .join(Student, Student.id == Enrollment.student_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .join(Course, Course.id == Cohort.course_id)
            .join(Branch, Branch.id == Cohort.branch_id)
            .outerjoin(AppUser, AppUser.id == Cohort.instructor_id)
            .where(Enrollment.id == enrollment_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    enrollment, student, cohort, course, branch, instructor = row
    results = await enrollment_results(db, None, enrollment_ids=[enrollment.id])
    first, last = split_name(student.full_name)
    issued = enrollment.certificate_issued_at
    values: dict[str, str | date] = {
        "student.full_name": student.full_name,
        "student.first_name": first,
        "student.last_name": last,
        "course.name": course.name,
        "course.direction": course.direction or "",
        "cohort.code": cohort.code,
        "cohort.start_date": cohort.start_date,
        "cohort.end_date": cohort.end_date,
        "branch.name": branch.name,
        "instructor.full_name": instructor.full_name if instructor else "",
        "certificate.number": enrollment.certificate_no or "",
        "grade.total": str(results[enrollment.id]["score"]),
    }
    if issued is not None:
        values["certificate.issued_date"] = issued.astimezone(TZ).date()
    ctx = Context(values, student.gender, enrollment.certificate_no or "")
    if instructor is not None and instructor.signature_asset_id is not None:
        ctx.instructor_signature_ref = str(instructor.signature_asset_id)
    apply_settings(ctx, await load_settings(db), lang)
    return ctx, cohort, course, instructor, enrollment


DATE_KEYS = ("cohort.start_date", "cohort.end_date", "certificate.issued_date")


def snapshot_of(ctx: Context, lang: str, custom: dict[str, str] | None = None) -> dict[str, Any]:
    """Everything a render of `ctx` needs, as JSON: stored with the certificate, so a later PDF
    does not depend on the student, the cohort, the settings or the instructor as they are then."""
    return {
        "values": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in ctx.values.items()},
        "gender": ctx.gender,
        "verify_code": ctx.verify_code,
        "verify_base": ctx.verify_base,
        "signature_ref": ctx.signature_ref,
        "seal_ref": ctx.seal_ref,
        "instructor_signature_ref": ctx.instructor_signature_ref,
        "lang": lang,
        "custom": custom or {},
    }


def context_of(data: dict[str, Any]) -> Context:
    values: dict[str, str | date] = {
        k: (date.fromisoformat(v) if k in DATE_KEYS and v else v) for k, v in data["values"].items()
    }
    return Context(
        values=values,
        gender=data.get("gender"),
        verify_code=data.get("verify_code", ""),
        verify_base=data.get("verify_base", ""),
        signature_ref=data.get("signature_ref"),
        seal_ref=data.get("seal_ref"),
        instructor_signature_ref=data.get("instructor_signature_ref"),
    )
