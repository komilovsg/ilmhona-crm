"""The public check page of a certificate (`/v/<code>` on the web), reached from its QR code or
by typing the code printed under it. No login.

It answers only what is printed on the certificate itself plus its status: number, holder, course,
the cohort dates when the template shows them, the issue date, and valid / replaced / revoked
(with the revoke date, never the reason). No ids, contacts, payments or comments.

The code is random (`new_verify_code`), never derived from the number, and only certificates
issued since this page exists have one. An unknown, old or malformed code gets the same
«not found» after the same single query; views are not audited (noise) and nothing personal is
logged. Each client address may check a few codes a minute.
"""

import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.certificates.errors import CERT_CHECK_LIMIT
from app.certificates.issuing import CODE_ALPHABET, CODE_LENGTH
from app.core.clock import TZ
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.proxy import client_ip
from app.core.ratelimit import SlidingWindow
from app.models import Certificate, CertTemplateVersion

router = APIRouter(prefix="/api/v1/public", tags=["public"])

ISSUER = "ilmhona"
PER_ADDRESS = SlidingWindow(limit=20, window_s=60)
EVERYONE = SlidingWindow(limit=600, window_s=60, max_keys=1)  # all addresses together
_CODE = re.compile(f"[{CODE_ALPHABET}]{{{CODE_LENGTH}}}")
_NEVER = "-"  # not a possible code: a malformed one still costs the same query
DATED = ("cohort.start_date", "cohort.end_date")


def normalize(raw: str) -> str | None:
    """The code as stored, from what a person typed or the QR held: case and dashes or spaces
    do not matter. None when it cannot be a code."""
    code = re.sub(r"[\s\-]", "", raw[:64]).upper()
    return code if _CODE.fullmatch(code) else None


def _fields_shown(layout: dict[str, Any]) -> set[str]:
    shown: set[str] = set()
    for layer in layout.get("layers", []):
        for run in layer.get("content", []) if layer.get("type") == "text" else []:
            if isinstance(run, dict) and isinstance(run.get("field"), str):
                shown.add(run["field"])
    return shown


def _day(value: Any) -> str | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10]).isoformat()


def _local_day(value: datetime | None) -> str | None:
    return value.astimezone(TZ).date().isoformat() if value else None


@router.get("/certificates/{code}")
async def check_certificate(code: str, request: Request, db: DB) -> dict[str, Any]:
    if not EVERYONE.allow("all") or not PER_ADDRESS.allow(client_ip(request)):
        raise DomainError(CERT_CHECK_LIMIT)
    found = (
        await db.execute(
            select(Certificate, CertTemplateVersion.layout)
            .join(CertTemplateVersion, CertTemplateVersion.id == Certificate.template_version_id)
            .where(Certificate.public_code == (normalize(code) or _NEVER))
        )
    ).first()
    if found is None:
        raise DomainError(NOT_FOUND)
    cert, layout = found
    values = cert.data.get("values", {})
    shown = _fields_shown(layout)
    start, end = (_day(values.get(k)) if k in shown else None for k in DATED)
    return {
        "number": cert.number,
        "holder": values.get("student.full_name") or "",
        "course": values.get("course.name") or "",
        "cohort_start": start,
        "cohort_end": end,
        "issued_on": _day(values.get("certificate.issued_date")) or _local_day(cert.issued_at),
        "status": cert.status,
        "revoked_on": _local_day(cert.revoked_at) if cert.status == "revoked" else None,
        "issuer": ISSUER,
    }
