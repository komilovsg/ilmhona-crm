"""Cohort analytics endpoint and its Excel file (SPEC «Аналитика потока»).

Rights: the same as the cohort's attendance and grades (`attendance` view; an instructor sees only
their own cohorts, a branch-bound user their branch, 404 for the rest). No money in the payload.
Phones appear only for users who may see the cohort's students (`cohorts` view).
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.education.scope import check_cohort_visible
from app.export import Col, Sheet, workbook_response
from app.metrics.cohort_analytics import cohort_analytics
from app.models import Cohort
from app.permissions import allows

router = APIRouter(
    prefix="/api/v1", tags=["attendance"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("attendance", "view")]
PERIOD_NAMES = {"week": "неделя", "month": "месяц", "course": "весь курс"}
Period = Annotated[Literal["week", "month", "course"], Query()]


async def _cohort(db: AsyncSession, p: Principal, cohort_id: uuid.UUID) -> Cohort:
    cohort = (await db.execute(select(Cohort).where(Cohort.id == cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)
    return cohort


def _phones(p: Principal) -> bool:
    return allows(p.level("cohorts"), "view")


@router.get("/cohorts/{cohort_id}/analytics")
async def analytics(
    cohort_id: uuid.UUID, p: View, db: DB, period: Period = "course"
) -> dict[str, Any]:
    cohort = await _cohort(db, p, cohort_id)
    return await cohort_analytics(db, cohort, period, with_phone=_phones(p))


def _reasons(r: dict[str, Any]) -> str:
    return "; ".join(x["text"] for x in r["reasons"])


@router.get("/cohorts/{cohort_id}/analytics/export")
async def export_analytics(
    cohort_id: uuid.UUID, p: View, db: DB, period: Period = "course"
) -> Response:
    """Sheets: end-of-course table (when available), «В зоне риска», «Отличники» — the rows of
    the screen."""
    cohort = await _cohort(db, p, cohort_id)
    data = await cohort_analytics(db, cohort, period, with_phone=_phones(p))
    sheets: list[Sheet[Any]] = []
    final = data["final"]
    if final["available"]:

        def points(key: str) -> Callable[[dict[str, Any]], Any]:
            return lambda r: r["points"][key]

        columns: list[Col[dict[str, Any]]] = [Col("Студент", lambda r: r["student_name"])]
        columns += [
            Col(f"{c['name']} (из {c['weight']})", points(c["key"]), "int")
            for c in final["categories"]
        ]
        columns += [
            Col("Итого", lambda r: r["total"], "int"),
            Col(f"Зачёт (от {final['pass_score']})", lambda r: r["passed"], "bool"),
            Col("Отличник", lambda r: r["excellent"], "bool"),
        ]
        sheets.append(Sheet("Итоги курса", columns, final["rows"]))
    risk_cols: list[Col[dict[str, Any]]] = [
        Col("Студент", lambda r: r["student_name"]),
        Col("Уровень", lambda r: "красный" if r["level"] == "red" else "оранжевый"),
        Col("Причины", _reasons),
    ]
    if _phones(p):
        risk_cols.insert(1, Col("Телефон", lambda r: r["phone"]))
    sheets.append(Sheet("В зоне риска", risk_cols, data["risk"]))
    sheets.append(
        Sheet(
            "Отличники",
            [
                Col("Студент", lambda r: r["student_name"]),
                Col("Посещаемость", lambda r: r["attendance_percent"], "percent"),
                Col("Прогноз", lambda r: r["projected"], "int"),
            ],
            data["top"],
        )
    )
    return await workbook_response(
        db,
        p,
        entity="cohort_analytics",
        slug=f"analitika_{cohort.code}",
        sheets=sheets,
        filters={"cohort": cohort.code, "period": PERIOD_NAMES[period]},
    )
